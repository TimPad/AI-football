from uuid import UUID
from fastapi import APIRouter,Depends,Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from aifootball.service.auth.security import require_admin,require_csrf
from aifootball.service.catalog.models import Team,Player,Entry
from aifootball.service.catalog.schemas import NamedCreate,NamedPatch,EntryCreate,RosterUpdate
from aifootball.service.catalog.operations import entry_view,roster_view,set_roster
from aifootball.service.common import get_entity,as_dict,list_entities
from aifootball.service.db import get_session
from aifootball.service.errors import DomainError
from aifootball.service.tournaments.models import Tournament

router=APIRouter()


def register_named(path,cls):
    def listing(db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
        return list_entities(db,cls,limit=limit,offset=offset)
    def create(data:NamedCreate,db:Session=Depends(get_session)):
        row=cls(**data.model_dump()); db.add(row); db.commit(); return as_dict(row)
    def update(entity_id:UUID,data:NamedPatch,db:Session=Depends(get_session)):
        with db.begin():
            row=get_entity(db,cls,entity_id,lock=True)
            values=data.model_dump(exclude_unset=True)
            if any(v is None for v in values.values()): raise DomainError('validation','Не очищайте обязательные поля')
            for key,value in values.items(): setattr(row,key,value)
        return as_dict(row)
    router.add_api_route(path,listing,methods=['GET'],dependencies=[Depends(require_admin)],name=f'list_{cls.__tablename__}')
    router.add_api_route(path,create,methods=['POST'],status_code=201,dependencies=[Depends(require_csrf)],name=f'create_{cls.__tablename__}')
    router.add_api_route(path+'/{entity_id}',update,methods=['PATCH'],dependencies=[Depends(require_csrf)],name=f'update_{cls.__tablename__}')


register_named('/teams',Team)
register_named('/players',Player)


@router.get('/tournaments/{tid}/entries',dependencies=[Depends(require_admin)])
def entries(tid:UUID,db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    get_entity(db,Tournament,tid)
    result=list_entities(db,Entry,where=[Entry.tournament_id==tid],limit=limit,offset=offset)
    result['items']=[entry_view(db,get_entity(db,Entry,row['id'])) for row in result['items']]
    return result


@router.post('/tournaments/{tid}/entries',status_code=201,dependencies=[Depends(require_csrf)])
def create_entry(tid:UUID,data:EntryCreate,db:Session=Depends(get_session)):
    with db.begin():
        tournament=get_entity(db,Tournament,tid); team=get_entity(db,Team,data.team_id)
        if tournament.archived or team.archived: raise DomainError('archived','Выбранная запись в архиве')
        entry=Entry(tournament_id=tid,team_id=data.team_id); db.add(entry); db.flush()
        result=entry_view(db,entry)
    return result


@router.get('/entries/{eid}/players',dependencies=[Depends(require_admin)])
def roster(eid:UUID,db:Session=Depends(get_session)):
    return roster_view(db,get_entity(db,Entry,eid))


@router.put('/entries/{eid}/players',dependencies=[Depends(require_csrf)])
def update_roster(eid:UUID,data:RosterUpdate,db:Session=Depends(get_session)):
    with db.begin(): return set_roster(db,get_entity(db,Entry,eid,lock=True),data)
