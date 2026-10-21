from uuid import UUID
from sqlalchemy import select
from aifootball.service.common import get_entity,as_dict
from aifootball.service.db import utcnow
from aifootball.service.errors import DomainError,RevisionConflict
from aifootball.service.catalog.models import Team,Player,TeamMember,Entry
from aifootball.service.tournaments.models import Tournament,RegulationVersion
from aifootball.service.captains.models import EntryInvitation,EntrySubmission,EntrySubmissionVersion
from aifootball.service.captains.security import require_captain_team

def tournament_option(t,invitation=None):
    return {'id':t.id,'name':t.name,'season':t.season,'timezone':t.timezone,'archived':t.archived,'applications_open':t.applications_open and not t.archived,'deadline':t.applications_deadline,'invitation_id':invitation.id if invitation else None}

def allowed_tournament(db,t,team_id,invitation_id=None,*,admission=False):
    query=select(EntryInvitation).where(EntryInvitation.team_id==team_id,EntryInvitation.tournament_id==t.id,EntryInvitation.active)
    if invitation_id:query=query.where(EntryInvitation.id==invitation_id)
    invitation=db.scalar(query)
    if (t.visibility!='public' and not invitation) or (invitation_id and not invitation):raise DomainError('not_found','Турнир недоступен',status=404)
    if admission and (t.archived or not t.applications_open or t.applications_deadline and t.applications_deadline<=utcnow()):raise DomainError('applications_closed','Подача заявок закрыта',status=409)
    return invitation

def own_submission(db,account,identifier,*,lock=False):
    row=get_entity(db,EntrySubmission,identifier)
    t=get_entity(db,Tournament,row.tournament_id,lock=lock)
    if lock:
        row=get_entity(db,EntrySubmission,identifier,lock=True);get_entity(db,Team,row.team_id,lock=True)
    require_captain_team(db,account,row.team_id);allowed_tournament(db,t,row.team_id)
    return row

def view(db,row,*,history=True,t=None,team=None,version=None):
    t=t or get_entity(db,Tournament,row.tournament_id);team=team or get_entity(db,Team,row.team_id)
    versions=list(db.scalars(select(EntrySubmissionVersion).where(EntrySubmissionVersion.submission_id==row.id).order_by(EntrySubmissionVersion.number.desc()))) if history else []
    if version is None:version=next((v for v in versions if v.id==row.submitted_version_id),None)
    return {**as_dict(row),'team_name':team.name,'tournament':tournament_option(t),'submitted_version':as_dict(version) if version else None,'versions':[as_dict(v) for v in versions]}

def snapshot(db,team,players,source_revision):
    if team.revision!=source_revision:raise DomainError('roster_changed','Состав команды изменился. Сравните его с черновиком заявки.',status=409)
    ids=[p.player_id for p in players];numbers=[p.shirt_number for p in players if p.shirt_number]
    if len(ids)!=len(set(ids)) or len(numbers)!=len(set(numbers)):raise DomainError('duplicate_roster','Игрок или номер повторяется в заявке')
    own={p.id:p for p in db.scalars(select(Player).join(TeamMember,TeamMember.player_id==Player.id).where(TeamMember.team_id==team.id,TeamMember.active,Player.archived.is_(False)))}
    if set(ids)-set(own):raise DomainError('not_found','Игрок недоступен для этой команды',status=404)
    return {'source_roster_revision':source_revision,'players':[{'player_id':str(p.player_id),'display_name':own[p.player_id].name,'shirt_number':p.shirt_number} for p in players]}

def entry_revision(db,tournament_id,team_id):
    entry=db.scalar(select(Entry).where(Entry.tournament_id==tournament_id,Entry.team_id==team_id))
    return entry.revision if entry else None

def check_submission_limit(db,row):
    if not row.draft['players']:raise DomainError('empty_roster','Добавьте хотя бы одного игрока в заявку')
    rules=db.scalar(select(RegulationVersion).where(RegulationVersion.tournament_id==row.tournament_id).order_by(RegulationVersion.created_at.desc(),RegulationVersion.id).limit(1))
    limit=rules.rules['tournament_roster_limit'] if rules else 1000
    if len(row.draft['players'])>limit:raise DomainError('roster_limit',f'В заявке не более {limit} игроков')
