from uuid import UUID
from fastapi import APIRouter,Depends,Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from aifootball.service.auth.security import require_admin,require_csrf
from aifootball.service.catalog.models import Team,Player,Entry,TeamMember
from aifootball.service.catalog.schemas import NamedCreate,NamedPatch,EntryCreate,RosterUpdate,PlayerCreate,PlayerPatch,TeamCreate,TeamPatch,TeamProfileUpdate,RosterPlayer
from aifootball.service.catalog.profiles import save_profile,team_profile,check_image
from aifootball.service.catalog.operations import entry_view,roster_view,set_roster
from aifootball.service.catalog.operations import enter_team
from aifootball.service.catalog.schemas import CreateTournamentTeam, AddTournamentTeams
from aifootball.service.tournaments.commands import setup_command, editable_tournament
from aifootball.service.common import get_entity,as_dict,list_entities
from aifootball.service.db import get_session
from aifootball.service.errors import DomainError
from aifootball.service.tournaments.models import Tournament

from aifootball.service.views import Page,NamedView,EntryView,RosterView,TeamView,PlayerView,TeamProfile

router=APIRouter()


def register_named(path,cls,create_schema,patch_schema,view):
    def listing(db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
        return list_entities(db,cls,limit=limit,offset=offset)
    def create(data:create_schema,db:Session=Depends(get_session)):
        with db.begin():
            if cls is Team: return save_profile(db,data)
            check_image(db,data.photo_id)
            row=cls(**data.model_dump()); db.add(row); db.flush(); return as_dict(row)
    def update(entity_id:UUID,data:patch_schema,db:Session=Depends(get_session)):
        with db.begin():
            row=get_entity(db,cls,entity_id,lock=True)
            values=data.model_dump(exclude_unset=True)
            if any(v is None for key,v in values.items() if key in {'name','archived','description'}): raise DomainError('validation','Не очищайте обязательные поля')
            check_image(db,values.get('logo_id') if cls is Team else values.get('photo_id'))
            for key,value in values.items(): setattr(row,key,value)
            row.revision+=1
        return as_dict(row)
    router.add_api_route(path,listing,methods=['GET'],response_model=Page[view],dependencies=[Depends(require_admin)],name=f'list_{cls.__tablename__}')
    router.add_api_route(path,create,methods=['POST'],response_model=TeamProfile if cls is Team else view,status_code=201,dependencies=[Depends(require_csrf)],name=f'create_{cls.__tablename__}')
    router.add_api_route(path+'/{entity_id}',update,methods=['PATCH'],response_model=view,dependencies=[Depends(require_csrf)],name=f'update_{cls.__tablename__}')


register_named('/teams',Team,TeamCreate,TeamPatch,TeamView)
register_named('/players',Player,PlayerCreate,PlayerPatch,PlayerView)

from aifootball.service.catalog.schemas import RosterProfileUpdate,PlayerDetails

@router.put('/entries/{entry_id}/roster',response_model=RosterView)
def save_entry_roster(entry_id:UUID,data:RosterProfileUpdate,admin=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        entry=get_entity(db,Entry,entry_id)
        tournament=get_entity(db,Tournament,entry.tournament_id,lock=True)
        if tournament.archived:raise DomainError('archived','Турнир в архиве')
        entry=get_entity(db,Entry,entry_id,lock=True)
        selected={p.player_id for p in data.players};new_ids=set()
        for p in data.new_players:
            if p.player_id in new_ids or p.player_id not in selected or p.revision!=0:raise DomainError('new_player','Новый игрок должен входить в заявку ровно один раз')
            if db.get(Player,p.player_id) is not None:raise DomainError('player_exists','UUID игрока уже существует. Выберите его из справочника.',status=409)
            new_ids.add(p.player_id);check_image(db,p.photo_id)
            db.add(Player(id=p.player_id,name=p.name,**{key:getattr(p,key) for key in PlayerDetails.model_fields}))
        db.flush()
        return set_roster(db,entry,data)
    with db.begin():return setup_command(db,admin.id,data.request_id,'entry-roster',{'entry_id':str(entry_id),**data.model_dump(mode='json',exclude={'request_id'})},execute)


@router.get('/teams/{team_id}',response_model=TeamProfile,dependencies=[Depends(require_admin)])
def detail(team_id:UUID,db:Session=Depends(get_session)):
    return team_profile(db,get_entity(db,Team,team_id))


@router.put('/teams/{team_id}/profile',response_model=TeamProfile,dependencies=[Depends(require_csrf)])
def profile(team_id:UUID,data:TeamProfileUpdate,db:Session=Depends(get_session)):
    with db.begin(): return save_profile(db,data,team_id)


@router.get('/tournaments/{tid}/entries',response_model=Page[EntryView],dependencies=[Depends(require_admin)])
def entries(tid:UUID,db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    get_entity(db,Tournament,tid)
    result=list_entities(db,Entry,where=[Entry.tournament_id==tid],limit=limit,offset=offset)
    result['items']=[entry_view(db,get_entity(db,Entry,row['id'])) for row in result['items']]
    return result


@router.post('/tournaments/{tid}/entries',response_model=EntryView,status_code=201,dependencies=[Depends(require_csrf)])
def create_entry(tid:UUID,data:EntryCreate,db:Session=Depends(get_session)):
    with db.begin():
        tournament=get_entity(db,Tournament,tid,lock=True); team=get_entity(db,Team,data.team_id)
        return enter_team(db,tournament,team)


@router.post('/tournaments/{tid}/teams',response_model=EntryView,status_code=201)
def create_tournament_team(tid:UUID,data:CreateTournamentTeam,admin=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        tournament=editable_tournament(db,tid,data.expected_tournament_revision)
        profile=save_profile(db,data.team)
        return enter_team(db,tournament,get_entity(db,Team,profile['id']))
    with db.begin():
        return setup_command(db,admin.id,data.request_id,'team-and-entry',
                             {'tournament_id':tid,**data.model_dump(mode='json')},execute)


@router.post('/tournaments/{tid}/entries/batch',response_model=list[EntryView],status_code=201)
def add_tournament_teams(tid:UUID,data:AddTournamentTeams,admin=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        tournament=editable_tournament(db,tid,data.expected_tournament_revision)
        result=[]
        for team_id in dict.fromkeys(data.team_ids):
            existing=db.scalar(select(Entry).where(Entry.tournament_id==tid,Entry.team_id==team_id))
            if existing:
                result.append(entry_view(db,existing))
            else:
                result.append(enter_team(db,tournament,get_entity(db,Team,team_id)))
        return result
    with db.begin():
        return setup_command(db,admin.id,data.request_id,'entries-batch',
                             {'tournament_id':tid,**data.model_dump(mode='json')},execute)


@router.get('/entries/{eid}/players',response_model=RosterView,dependencies=[Depends(require_admin)])
def roster(eid:UUID,db:Session=Depends(get_session)):
    return roster_view(db,get_entity(db,Entry,eid))


@router.put('/entries/{eid}/players',response_model=RosterView,dependencies=[Depends(require_csrf)])
def update_roster(eid:UUID,data:RosterUpdate,db:Session=Depends(get_session)):
    with db.begin(): return set_roster(db,get_entity(db,Entry,eid,lock=True),data)


@router.get('/players/{player_id}', response_model=PlayerView, dependencies=[Depends(require_admin)])
def player_detail(player_id: UUID, db: Session=Depends(get_session)):
    return as_dict(get_entity(db, Player, player_id))
