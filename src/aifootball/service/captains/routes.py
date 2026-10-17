from datetime import timedelta
from secrets import token_urlsafe
from uuid import UUID
from fastapi import APIRouter,Depends,Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from aifootball.service.db import get_session,utcnow
from aifootball.service.common import get_entity,as_dict
from aifootball.service.auth.security import require_csrf,require_admin,token_hash
from aifootball.service.catalog.models import Team
from aifootball.service.catalog.profiles import team_profile
from aifootball.service.views import Page,TeamProfile
from aifootball.service.errors import DomainError
from aifootball.service.tournaments.commands import setup_command
from aifootball.service.captains.models import CaptainAccount,TeamCaptainGrant,TeamCaptainInvitation,CaptainGrantAudit,CaptainOwnershipRequest
from aifootball.service.captains.schemas import InvitationCreate,InvitationView,TokenInput,GrantView,ReasonCommand,GrantCreate,OwnershipRequest
from aifootball.service.captains.security import require_captain,require_captain_csrf,require_captain_team
from aifootball.service.captains.commands import command
from aifootball.service.captains.mail import enqueue,require_transport

router=APIRouter()

def grant_team(db,team_id,account_id,actor,reason,replace=False):
    team=get_entity(db,Team,team_id,lock=True);account=get_entity(db,CaptainAccount,account_id)
    if team.archived or not account.active or not account.verified_at:raise DomainError('captain_access','Команда или капитан недоступны',status=409)
    old=db.scalar(select(TeamCaptainGrant).where(TeamCaptainGrant.team_id==team_id,TeamCaptainGrant.active))
    if old and old.account_id==account_id:return as_dict(old)
    if old:
        if not replace:raise DomainError('captain_exists','У команды уже есть капитан. Для передачи укажите причину.',status=409)
        old.active=False;db.add(CaptainGrantAudit(grant_id=old.id,actor_id=actor,action='revoke',reason=reason));db.flush()
    grant=TeamCaptainGrant(team_id=team_id,account_id=account_id);db.add(grant);db.flush()
    db.add(CaptainGrantAudit(grant_id=grant.id,actor_id=actor,action='grant',reason=reason));return as_dict(grant)

@router.get('/captain/teams',response_model=Page[TeamProfile])
def own_teams(account=Depends(require_captain),db:Session=Depends(get_session)):
    rows=db.scalars(select(Team).join(TeamCaptainGrant,TeamCaptainGrant.team_id==Team.id).where(TeamCaptainGrant.account_id==account.id,TeamCaptainGrant.active).order_by(Team.name,Team.id)).all()
    return {'items':[team_profile(db,row) for row in rows],'total':len(rows)}

@router.get('/captain/teams/{team_id}',response_model=TeamProfile)
def own_team(team_id:UUID,account=Depends(require_captain),db:Session=Depends(get_session)):
    require_captain_team(db,account,team_id);return team_profile(db,get_entity(db,Team,team_id))

@router.post('/teams/{team_id}/captain-invitations',response_model=InvitationView,status_code=201)
def invite(team_id:UUID,data:InvitationCreate,request:Request,actor=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        team=get_entity(db,Team,team_id,lock=True)
        if team.archived:raise DomainError('archived','Команда в архиве',status=409)
        require_transport(request.app);token=token_urlsafe(32);expires=utcnow()+timedelta(hours=72)
        invitation=TeamCaptainInvitation(team_id=team_id,email=data.email,token_hash=token_hash(token),expires_at=expires,created_by=actor.id);db.add(invitation);db.flush()
        enqueue(db,request.app,'invitation',data.email,token,expires);return InvitationView.model_validate(as_dict(invitation)).model_dump(mode='json')
    with db.begin():return setup_command(db,actor.id,data.request_id,'captain-invite',{'team_id':team_id,**data.model_dump()},execute)

@router.post('/teams/{team_id}/captain-invitations/{invite_id}/revoke',response_model=InvitationView)
def revoke_invite(team_id:UUID,invite_id:UUID,data:ReasonCommand,actor=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        invitation=get_entity(db,TeamCaptainInvitation,invite_id,lock=True)
        if invitation.team_id!=team_id:raise DomainError('not_found','Приглашение не найдено',status=404)
        invitation.revoked_at=utcnow();return InvitationView.model_validate(as_dict(invitation)).model_dump(mode='json')
    with db.begin():return setup_command(db,actor.id,data.request_id,'captain-invite-revoke',{'team_id':team_id,'invite_id':invite_id,**data.model_dump()},execute)

@router.post('/captain/invitations/accept',response_model=GrantView)
def accept_invite(data:TokenInput,account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    def execute():
        invitation=db.scalar(select(TeamCaptainInvitation).where(TeamCaptainInvitation.token_hash==token_hash(data.token)).with_for_update())
        if not invitation or invitation.email!=account.email or invitation.revoked_at or invitation.expires_at<=utcnow():raise DomainError('not_found','Приглашение недействительно',status=404)
        if invitation.used_at:raise DomainError('invite_used','Приглашение уже использовано',status=409)
        grant=grant_team(db,invitation.team_id,account.id,invitation.created_by,'Приглашение принято капитаном')
        invitation.used_at=utcnow();return grant
    # Journal stores a token hash, never the raw invitation secret.
    with db.begin():return command(db,account.id,data.request_id,'accept-invite',{'token_hash':token_hash(data.token)},execute)

@router.post('/teams/{team_id}/captain-grants',response_model=GrantView)
def create_grant(team_id:UUID,data:GrantCreate,actor=Depends(require_csrf),db:Session=Depends(get_session)):
    with db.begin():return setup_command(db,actor.id,data.request_id,'captain-grant',{'team_id':team_id,**data.model_dump()},lambda:grant_team(db,team_id,data.account_id,actor.id,data.reason,data.replace))

@router.post('/teams/{team_id}/captain-grants/{grant_id}/revoke',response_model=GrantView)
def revoke_grant(team_id:UUID,grant_id:UUID,data:ReasonCommand,actor=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        get_entity(db,Team,team_id,lock=True);grant=get_entity(db,TeamCaptainGrant,grant_id,lock=True)
        if grant.team_id!=team_id:raise DomainError('not_found','Доступ не найден',status=404)
        grant.active=False;db.add(CaptainGrantAudit(grant_id=grant.id,actor_id=actor.id,action='revoke',reason=data.reason));return as_dict(grant)
    with db.begin():return setup_command(db,actor.id,data.request_id,'captain-revoke',{'team_id':team_id,'grant_id':grant_id,**data.model_dump()},execute)

@router.get('/teams/{team_id}/captain-access',dependencies=[Depends(require_admin)])
def access(team_id:UUID,db:Session=Depends(get_session)):
    get_entity(db,Team,team_id)
    grants=db.execute(select(TeamCaptainGrant,CaptainAccount).join(CaptainAccount,CaptainAccount.id==TeamCaptainGrant.account_id).where(TeamCaptainGrant.team_id==team_id)).all()
    requests=db.execute(select(CaptainOwnershipRequest,CaptainAccount).join(CaptainAccount,CaptainAccount.id==CaptainOwnershipRequest.account_id).where(CaptainOwnershipRequest.team_id==team_id,CaptainOwnershipRequest.status=='pending')).all()
    return {'grants':[{**as_dict(g),'email':a.email,'display_name':a.display_name} for g,a in grants],
            'invitations':[InvitationView.model_validate(as_dict(row)).model_dump() for row in db.scalars(select(TeamCaptainInvitation).where(TeamCaptainInvitation.team_id==team_id))],
            'requests':[{**as_dict(r),'email':a.email,'display_name':a.display_name} for r,a in requests]}

@router.post('/captain/ownership-requests',status_code=201)
def ownership(data:OwnershipRequest,account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    def execute():
        from aifootball.service.catalog.models import Entry
        from aifootball.service.tournaments.models import Tournament
        visible=db.scalar(select(Team.id).join(Entry,Entry.team_id==Team.id).join(Tournament,Tournament.id==Entry.tournament_id).where(Team.id==data.team_id,Team.archived.is_(False),Tournament.archived.is_(False),Tournament.visibility=='public'))
        if not visible:raise DomainError('not_found','Команда недоступна для запроса',status=404)
        prior=db.scalar(select(CaptainOwnershipRequest).where(CaptainOwnershipRequest.account_id==account.id,CaptainOwnershipRequest.team_id==data.team_id,CaptainOwnershipRequest.status=='pending'))
        if prior:return as_dict(prior)
        row=CaptainOwnershipRequest(account_id=account.id,team_id=data.team_id,message=data.message);db.add(row);db.flush();return as_dict(row)
    with db.begin():return command(db,account.id,data.request_id,'ownership-request',data.model_dump(),execute)

@router.post('/teams/{team_id}/captain-requests/{request_id}/accept',response_model=GrantView)
def approve(team_id:UUID,request_id:UUID,data:ReasonCommand,actor=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        row=get_entity(db,CaptainOwnershipRequest,request_id,lock=True)
        if row.team_id!=team_id or row.status!='pending':raise DomainError('not_found','Запрос недоступен',status=404)
        result=grant_team(db,team_id,row.account_id,actor.id,data.reason);row.status='accepted';return result
    with db.begin():return setup_command(db,actor.id,data.request_id,'captain-request-accept',{'team_id':team_id,'ownership_request_id':request_id,**data.model_dump()},execute)
