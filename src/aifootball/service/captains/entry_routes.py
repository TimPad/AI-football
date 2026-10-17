from copy import deepcopy
from uuid import UUID,uuid5
from fastapi import APIRouter,Depends,Query
from sqlalchemy import select,func,or_,exists
from sqlalchemy.orm import Session
from aifootball.service.db import get_session
from aifootball.service.common import get_entity,as_dict
from aifootball.service.errors import DomainError,RevisionConflict
from aifootball.service.auth.security import require_admin,require_csrf
from aifootball.service.catalog.models import Team,TeamMember,Entry
from aifootball.service.catalog.schemas import RosterPlayer,RosterUpdate
from aifootball.service.catalog.operations import set_roster
from aifootball.service.tournaments.models import Tournament
from aifootball.service.tournaments.commands import setup_command
from aifootball.service.captains.models import EntrySubmission,EntrySubmissionVersion,EntryInvitation,TeamCaptainGrant
from aifootball.service.captains.security import require_captain,require_captain_csrf,require_captain_team
from aifootball.service.captains.commands import command
from aifootball.service.captains.entry_schemas import ApplicationCreate,ApplicationCommand,ApplicationDraft,ApplicationDecision,ApplicationSettings,EntryInvitationCreate,ApplicationView,CaptainTournamentOption,EntryInvitationView
from aifootball.service.captains.entries import view,snapshot,entry_revision,check_submission_limit,allowed_tournament,own_submission,tournament_option
from aifootball.service.views import Page,TournamentView

router=APIRouter()

@router.post('/captain/tournaments/{tid}/applications',response_model=ApplicationView,status_code=201)
def create(tid:UUID,data:ApplicationCreate,account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    def execute():
        t=get_entity(db,Tournament,tid,lock=True);team=get_entity(db,Team,data.team_id,lock=True);require_captain_team(db,account,team.id)
        allowed_tournament(db,t,team.id,data.invitation_id,admission=True)
        if team.archived:raise DomainError('archived','Команда находится в архиве',status=409)
        prior=db.scalar(select(EntrySubmission).where(EntrySubmission.tournament_id==tid,EntrySubmission.team_id==team.id))
        if prior:return view(db,prior)
        players=[RosterPlayer(player_id=m.player_id,shirt_number=m.shirt_number) for m in db.scalars(select(TeamMember).where(TeamMember.team_id==team.id,TeamMember.active).order_by(TeamMember.created_at,TeamMember.id))]
        payload={**snapshot(db,team,players,team.revision),'expected_entry_revision':entry_revision(db,tid,team.id)}
        row=EntrySubmission(tournament_id=tid,team_id=team.id,created_by=account.id,draft=payload);db.add(row);db.flush();return view(db,row)
    with db.begin():
        require_captain_team(db,account,data.team_id)
        allowed_tournament(db,get_entity(db,Tournament,tid),data.team_id,data.invitation_id)
        return command(db,account.id,data.request_id,'application-create',{'tid':tid,**data.model_dump()},execute)

@router.get('/captain/applications/{identifier}',response_model=ApplicationView)
def detail(identifier:UUID,account=Depends(require_captain),db:Session=Depends(get_session)):
    return view(db,own_submission(db,account,identifier))

@router.put('/captain/applications/{identifier}/draft',response_model=ApplicationView)
def save_draft(identifier:UUID,data:ApplicationDraft,account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    def execute():
        row=own_submission(db,account,identifier,lock=True);t=get_entity(db,Tournament,row.tournament_id);team=get_entity(db,Team,row.team_id)
        if row.revision!=data.expected_revision:raise RevisionConflict(row.revision)
        if t.archived or team.archived:raise DomainError('archived','Турнир или команда в архиве',status=409)
        row.draft={**snapshot(db,team,data.players,data.source_roster_revision),'expected_entry_revision':entry_revision(db,t.id,team.id)}
        row.status='draft';row.revision+=1;db.flush();return view(db,row)
    with db.begin():
        own_submission(db,account,identifier)
        return command(db,account.id,data.request_id,'application-draft',{'id':identifier,**data.model_dump()},execute)

@router.post('/captain/applications/{identifier}/submit',response_model=ApplicationView)
def submit(identifier:UUID,data:ApplicationCommand,account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    def execute():
        row=own_submission(db,account,identifier,lock=True);t=get_entity(db,Tournament,row.tournament_id);team=get_entity(db,Team,row.team_id)
        if row.revision!=data.expected_revision:raise RevisionConflict(row.revision)
        if row.status=='submitted':raise DomainError('already_submitted','Эта версия уже отправлена',status=409)
        allowed_tournament(db,t,team.id,admission=True)
        if team.archived:raise DomainError('archived','Команда в архиве',status=409)
        snapshot(db,team,[RosterPlayer(player_id=p['player_id'],shirt_number=p['shirt_number']) for p in row.draft['players']],row.draft['source_roster_revision'])
        if entry_revision(db,t.id,team.id)!=row.draft.get('expected_entry_revision'):raise DomainError('entry_changed','Организатор изменил заявку. Сохраните новый черновик после сравнения.',status=409)
        check_submission_limit(db,row)
        number=(db.scalar(select(func.max(EntrySubmissionVersion.number)).where(EntrySubmissionVersion.submission_id==row.id)) or 0)+1
        version=EntrySubmissionVersion(id=uuid5(row.id,'submission:'+str(data.request_id)),submission_id=row.id,actor_id=account.id,number=number,payload=deepcopy(row.draft));db.add(version);db.flush()
        row.submitted_version_id=version.id;row.status='submitted';row.reason='';row.revision+=1;db.flush();return view(db,row)
    with db.begin():
        own_submission(db,account,identifier)
        return command(db,account.id,data.request_id,'application-submit',{'id':identifier,**data.model_dump()},execute)

def list_applications(db,query,limit,offset):
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.execute(query.order_by(EntrySubmission.created_at.desc(),EntrySubmission.id).limit(limit).offset(offset)).all()
    return {'total':total,'items':[view(db,row,history=False,t=t,team=team,version=version) for row,t,team,version in rows]}

def application_query():
    return select(EntrySubmission,Tournament,Team,EntrySubmissionVersion).join(Tournament,Tournament.id==EntrySubmission.tournament_id).join(Team,Team.id==EntrySubmission.team_id).outerjoin(EntrySubmissionVersion,EntrySubmissionVersion.id==EntrySubmission.submitted_version_id)

@router.get('/captain/teams/{team_id}/applications',response_model=Page[ApplicationView])
def own_list(team_id:UUID,account=Depends(require_captain),db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    require_captain_team(db,account,team_id)
    invited=exists(select(EntryInvitation.id).where(EntryInvitation.tournament_id==Tournament.id,EntryInvitation.team_id==team_id,EntryInvitation.active))
    return list_applications(db,application_query().where(EntrySubmission.team_id==team_id,or_(Tournament.visibility=='public',invited)),limit,offset)

@router.get('/tournaments/{tid}/applications',response_model=Page[ApplicationView],dependencies=[Depends(require_admin)])
def admin_list(tid:UUID,db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),status:str|None=Query(None,max_length=30)):
    get_entity(db,Tournament,tid);query=application_query().where(EntrySubmission.tournament_id==tid)
    if status:query=query.where(EntrySubmission.status==status)
    return list_applications(db,query,limit,offset)

@router.post('/tournaments/{tid}/applications/{identifier}/accept',response_model=ApplicationView)
def accept(tid:UUID,identifier:UUID,data:ApplicationDecision,actor=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        t=get_entity(db,Tournament,tid,lock=True);row=get_entity(db,EntrySubmission,identifier,lock=True);team=get_entity(db,Team,row.team_id,lock=True)
        if row.tournament_id!=tid:raise DomainError('not_found','Заявка не найдена',status=404)
        if row.revision!=data.expected_revision:raise RevisionConflict(row.revision)
        if row.status!='submitted' or not data.version_id or data.version_id!=row.submitted_version_id:raise DomainError('application_changed','Выберите текущую отправленную версию',status=409)
        if t.archived or team.archived:raise DomainError('archived','Турнир или команда в архиве',status=409)
        version=get_entity(db,EntrySubmissionVersion,data.version_id)
        entry=db.scalar(select(Entry).where(Entry.tournament_id==tid,Entry.team_id==team.id).with_for_update())
        if (entry.revision if entry else None)!=version.payload.get('expected_entry_revision'):raise DomainError('entry_changed','Заявка турнира уже изменена. Верните капитану для сверки.',status=409)
        if entry is None:entry=Entry(tournament_id=tid,team_id=team.id);db.add(entry);db.flush()
        set_roster(db,entry,RosterUpdate(expected_revision=entry.revision,players=[RosterPlayer(player_id=p['player_id'],shirt_number=p['shirt_number']) for p in version.payload['players']]))
        row.accepted_version_id=version.id;row.status='accepted';row.reason=data.reason;row.revision+=1;db.flush();return view(db,row)
    with db.begin():return setup_command(db,actor.id,data.request_id,'application-accept',{'tid':tid,'id':identifier,**data.model_dump()},execute)

@router.post('/tournaments/{tid}/applications/{identifier}/request-changes',response_model=ApplicationView)
def request_changes(tid:UUID,identifier:UUID,data:ApplicationDecision,actor=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        get_entity(db,Tournament,tid,lock=True);row=get_entity(db,EntrySubmission,identifier,lock=True)
        if row.tournament_id!=tid:raise DomainError('not_found','Заявка не найдена',status=404)
        if row.revision!=data.expected_revision:raise RevisionConflict(row.revision)
        if row.status!='submitted':raise DomainError('application_changed','Заявка сейчас не на рассмотрении',status=409)
        row.status='changes_requested';row.reason=data.reason;row.revision+=1;db.flush();return view(db,row)
    with db.begin():return setup_command(db,actor.id,data.request_id,'application-return',{'tid':tid,'id':identifier,**data.model_dump()},execute)

@router.put('/tournaments/{tid}/applications/settings',response_model=TournamentView)
def settings(tid:UUID,data:ApplicationSettings,actor=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        t=get_entity(db,Tournament,tid,lock=True)
        if t.revision!=data.expected_revision:raise RevisionConflict(t.revision)
        if t.archived:raise DomainError('archived','Турнир в архиве',status=409)
        t.applications_open=data.applications_open;t.applications_deadline=data.deadline;t.revision+=1;db.flush();return as_dict(t)
    with db.begin():return setup_command(db,actor.id,data.request_id,'application-settings',{'tid':tid,**data.model_dump()},execute)

@router.post('/tournaments/{tid}/entry-invitations',status_code=201)
def invite(tid:UUID,data:EntryInvitationCreate,actor=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        t=get_entity(db,Tournament,tid,lock=True);team=get_entity(db,Team,data.team_id,lock=True)
        if t.archived or team.archived:raise DomainError('archived','Турнир или команда в архиве',status=409)
        if not db.scalar(select(TeamCaptainGrant.id).where(TeamCaptainGrant.team_id==team.id,TeamCaptainGrant.active)):raise DomainError('captain_required','Сначала пригласите капитана команды',status=409)
        row=db.scalar(select(EntryInvitation).where(EntryInvitation.tournament_id==tid,EntryInvitation.team_id==team.id,EntryInvitation.active))
        if row is None:row=EntryInvitation(tournament_id=tid,team_id=team.id,created_by=actor.id);db.add(row);db.flush()
        return as_dict(row)
    with db.begin():return setup_command(db,actor.id,data.request_id,'entry-invite',{'tid':tid,**data.model_dump()},execute)

@router.get('/tournaments/{tid}/entry-invitations',response_model=Page[EntryInvitationView],dependencies=[Depends(require_admin)])
def invitations(tid:UUID,db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    get_entity(db,Tournament,tid)
    query=select(EntryInvitation,Team.name).join(Team,Team.id==EntryInvitation.team_id).where(EntryInvitation.tournament_id==tid)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items':[{**as_dict(row),'team_name':name} for row,name in db.execute(query.order_by(EntryInvitation.created_at.desc()).limit(limit).offset(offset))],'total':total}

@router.post('/tournaments/{tid}/entry-invitations/{identifier}/revoke')
def revoke(tid:UUID,identifier:UUID,data:ApplicationCommand,actor=Depends(require_csrf),db:Session=Depends(get_session)):
    def execute():
        row=get_entity(db,EntryInvitation,identifier,lock=True)
        if row.tournament_id!=tid:raise DomainError('not_found','Приглашение недоступно',status=404)
        row.active=False;return as_dict(row)
    with db.begin():return setup_command(db,actor.id,data.request_id,'entry-invite-revoke',{'tid':tid,'id':identifier,**data.model_dump()},execute)

@router.get('/captain/teams/{team_id}/tournament-options',response_model=Page[CaptainTournamentOption])
def options(team_id:UUID,account=Depends(require_captain),db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    require_captain_team(db,account,team_id)
    query=select(Tournament,EntryInvitation).outerjoin(EntryInvitation,(EntryInvitation.tournament_id==Tournament.id)&(EntryInvitation.team_id==team_id)&EntryInvitation.active).where(Tournament.archived.is_(False),or_(Tournament.visibility=='public',EntryInvitation.id.is_not(None)))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items':[tournament_option(t,i) for t,i in db.execute(query.order_by(Tournament.name,Tournament.id).limit(limit).offset(offset))],'total':total}
