from uuid import UUID,uuid5
from pathlib import Path
from fastapi import APIRouter,Depends,Request,File,UploadFile,Header
from fastapi.responses import FileResponse
from sqlalchemy import select,or_
from sqlalchemy.orm import Session
from pydantic import Field
from aifootball.service.db import get_session
from aifootball.service.common import get_entity,as_dict
from aifootball.service.views import TeamProfile,CatalogImageView
from aifootball.service.catalog.schemas import TeamCreate,TeamProfileUpdate,ProfilePlayer,PlayerDetails
from aifootball.service.catalog.models import Team,Player,TeamMember
from aifootball.service.auth.security import require_csrf,require_admin
from aifootball.service.captains.security import require_captain,require_captain_csrf,require_captain_team
from aifootball.service.captains.commands import command
from aifootball.service.captains.models import CaptainImage,TeamCaptainGrant,PlayerProfileProposal
from aifootball.service.captains.teams import save_team,allowed_image,captain_team_view
from aifootball.service.captains.schemas import ReasonCommand
from aifootball.service.tournaments.commands import setup_command
from aifootball.service.errors import DomainError

router=APIRouter()
class CaptainTeamView(TeamProfile):
    profile_proposals:list[dict]=Field(default_factory=list)
class ProfileProposalDecision(ReasonCommand):
    create_new:bool=False
    use_existing_player_id:UUID|None=None
class ProfileProposalCreate(ProfilePlayer):
    request_id:UUID

@router.post('/captain/teams',response_model=CaptainTeamView,status_code=201)
def create(data:TeamCreate,account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    with db.begin():
        identifier=uuid5(account.id,'team:'+str(data.request_id))
        if db.get(Team,identifier):
            get_entity(db,Team,identifier,lock=True);require_captain_team(db,account,identifier)
        return command(db,account.id,data.request_id,'create-team',data.model_dump(),lambda:save_team(db,account,data))

@router.put('/captain/teams/{team_id}',response_model=CaptainTeamView)
def update(team_id:UUID,data:TeamProfileUpdate,account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    with db.begin():
        get_entity(db,Team,team_id,lock=True);require_captain_team(db,account,team_id)
        return command(db,account.id,data.request_id,'update-team',{'team_id':team_id,**data.model_dump()},lambda:save_team(db,account,data,team_id))

@router.post('/captain/teams/{team_id}/profile-proposals',status_code=201)
def propose(team_id:UUID,data:ProfileProposalCreate,account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    def execute():
        get_entity(db,Team,team_id,lock=True);require_captain_team(db,account,team_id)
        member=db.scalar(select(TeamMember).where(TeamMember.team_id==team_id,TeamMember.player_id==data.player_id,TeamMember.active))
        person=db.get(Player,data.player_id)
        if person and not member:raise DomainError('not_found','Игрок недоступен',status=404)
        allowed_image(db,account,data.photo_id,get_entity(db,Team,team_id))
        row=PlayerProfileProposal(account_id=account.id,team_id=team_id,player_id=person.id if person else None,expected_player_revision=person.revision if person else None,payload=data.model_dump(mode='json',exclude={'player_id','revision','request_id'}));db.add(row);db.flush();return as_dict(row)
    with db.begin():
        get_entity(db,Team,team_id,lock=True);require_captain_team(db,account,team_id)
        return command(db,account.id,data.request_id,'profile-proposal',{'team_id':team_id,**data.model_dump()},execute)

@router.get('/teams/{team_id}/profile-proposals',dependencies=[Depends(require_admin)])
def proposals(team_id:UUID,db:Session=Depends(get_session)):
    get_entity(db,Team,team_id);rows=db.scalars(select(PlayerProfileProposal).where(PlayerProfileProposal.team_id==team_id,PlayerProfileProposal.status=='pending')).all()
    return {'items':[as_dict(p) for p in rows],'total':len(rows)}

@router.post('/teams/{team_id}/profile-proposals/{proposal_id}/accept')
def accept(team_id:UUID,proposal_id:UUID,data:ProfileProposalDecision,actor=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        team=get_entity(db,Team,team_id,lock=True);proposal=get_entity(db,PlayerProfileProposal,proposal_id,lock=True)
        if proposal.team_id!=team_id or proposal.status!='pending' or team.archived:raise DomainError('not_found','Предложение недоступно',status=404)
        if not db.scalar(select(TeamCaptainGrant.id).where(TeamCaptainGrant.team_id==team_id,TeamCaptainGrant.account_id==proposal.account_id,TeamCaptainGrant.active)):raise DomainError('captain_access','Доступ автора отозван',status=409)
        details={key:proposal.payload.get(key) for key in ['name',*PlayerDetails.model_fields]}
        if proposal.player_id:
            person=get_entity(db,Player,proposal.player_id,lock=True)
            if person.revision!=proposal.expected_player_revision:raise DomainError('player_conflict','Карточка уже изменена. Сравните предложение заново.',status=409)
            if not db.scalar(select(TeamMember.id).where(TeamMember.team_id==team_id,TeamMember.player_id==person.id,TeamMember.active)):raise DomainError('roster_changed','Игрок больше не в составе команды',status=409)
            valid=ProfilePlayer(player_id=person.id,**details)
            for key,value in valid.model_dump(exclude={'player_id','revision','shirt_number'}).items():setattr(person,key,value)
            person.revision+=1
        else:
            if data.use_existing_player_id:person=get_entity(db,Player,data.use_existing_player_id,lock=True)
            elif data.create_new:
                valid=ProfilePlayer(player_id=uuid5(proposal.id,'approved-player'),**details)
                person=Player(id=valid.player_id,**valid.model_dump(exclude={'player_id','revision','shirt_number'}));db.add(person);db.flush()
            else:raise DomainError('profile_decision','Явно выберите существующего человека или создание нового.',status=422)
            if person.archived:raise DomainError('archived','Карточка игрока в архиве',status=409)
            member=db.scalar(select(TeamMember).where(TeamMember.team_id==team_id,TeamMember.player_id==person.id))
            if member is None:member=TeamMember(team_id=team_id,player_id=person.id);db.add(member)
            number=proposal.payload.get('shirt_number')
            if number and db.scalar(select(TeamMember.id).where(TeamMember.team_id==team_id,TeamMember.active,TeamMember.shirt_number==number,TeamMember.player_id!=person.id)):raise DomainError('duplicate_roster','Номер уже занят',status=409)
            member.active=True;member.shirt_number=number
        proposal.status='accepted';team.revision+=1;db.flush();return as_dict(proposal)
    with db.begin():return setup_command(db,actor.id,data.request_id,'profile-proposal-accept',{'team_id':team_id,'proposal_id':proposal_id,**data.model_dump()},execute)

@router.post('/captain/images',response_model=CatalogImageView,status_code=201)
def upload_image(request:Request,file:UploadFile=File(),request_id:UUID=Header(alias='X-Request-ID'),account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    from aifootball.service.catalog.images import upload
    # Distinct per-account namespace prevents claiming another uploader's request ID.
    result=upload(request,file,uuid5(account.id,'image:'+str(request_id)),db,account)
    with db.begin():
        if db.get(CaptainImage,result['id']) is None:db.add(CaptainImage(image_id=result['id'],account_id=account.id))
    return result

@router.get('/captain/images/{image_id}')
def image(image_id:UUID,request:Request,account=Depends(require_captain),db:Session=Depends(get_session)):
    owned=db.scalar(select(CaptainImage.image_id).where(CaptainImage.image_id==image_id,CaptainImage.account_id==account.id))
    team=db.scalar(select(Team.id).join(TeamCaptainGrant,TeamCaptainGrant.team_id==Team.id).where(TeamCaptainGrant.account_id==account.id,TeamCaptainGrant.active,Team.logo_id==image_id))
    photo=db.scalar(select(Player.id).join(TeamMember,TeamMember.player_id==Player.id).join(TeamCaptainGrant,TeamCaptainGrant.team_id==TeamMember.team_id).where(TeamCaptainGrant.account_id==account.id,TeamCaptainGrant.active,TeamMember.active,Player.photo_id==image_id))
    path=Path(request.app.state.settings.attachment_root)/'catalog'/(str(image_id)+'.png')
    if not(owned or team or photo) or not path.is_file():raise DomainError('not_found','Изображение недоступно',status=404)
    return FileResponse(path,media_type='image/png',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
