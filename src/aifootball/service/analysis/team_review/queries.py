from sqlalchemy import select
from aifootball.service.analysis.models import AnalysisJob,AnalysisRun,AnalysisAssignment
from aifootball.service.analysis.context import context_hash,build_context
from aifootball.service.captains.models import TeamCaptainGrant
from aifootball.service.captains.security import require_captain_team
from aifootball.service.common import get_entity
from aifootball.service.db import utcnow
from aifootball.service.errors import DomainError
from aifootball.service.matches.models import Match
from .models import TeamIdentityReviewTask,TeamIdentityConfirmation

def side_material(run,job,side):
    tracks={t['track_id']:t for t in run.tracks['tracks'] if t['role'] in ('player','goalkeeper') and run.side_map.get(t['team'])==side}
    groups=[];seen=set()
    for g in run.tracks.get('groups',[]):
        ids=sorted(g['track_ids'])
        # A mixed group must be repaired by Admin+, never silently split for a captain.
        if set(ids)&tracks.keys():
            if not set(ids)<=tracks.keys() or seen.intersection(ids):raise DomainError('material_groups','Исправьте смешанную или повторяющуюся группу перед выдачей',status=409)
            groups.append(ids);seen.update(ids)
    groups.extend([[tid] for tid in sorted(tracks) if tid not in seen]);groups.sort(key=lambda g:g[0])
    players=[{k:p.get(k) for k in ('player_id','display_name','shirt_number')} for p in job.context['rosters'] if p['side']==side]
    fingerprint=context_hash({'side_map':run.side_map,'groups':groups,'tracks':[tracks[k] for k in sorted(tracks)],'players':players})
    return tracks,groups,players,fingerprint

def assignment_fingerprint(db,run,track_ids):
    rows=db.scalars(select(AnalysisAssignment).where(AnalysisAssignment.run_id==run.id,AnalysisAssignment.track_id.in_(track_ids)).order_by(AnalysisAssignment.track_id)).all()
    return context_hash([{'track_id':a.track_id,'player_id':str(a.player_id) if a.player_id else None,'excluded_reason':a.excluded_reason} for a in rows])

def task_status(db,task,run=None,job=None):
    if task.status in ('revoked','obsolete'):return task.status
    run=run or get_entity(db,AnalysisRun,task.run_id);job=job or get_entity(db,AnalysisJob,run.job_id)
    try:
        current=side_material(run,job,task.side)[3]
        live_hash=context_hash(build_context(db,run.match_id,lock=False))
    except DomainError:return 'obsolete'
    grant=db.get(TeamCaptainGrant,task.grant_id)
    if (not grant or not grant.active or task.expires_at<=utcnow() or current!=task.group_fingerprint or
        live_hash!=task.context_hash or
        assignment_fingerprint(db,run,task.allowed_track_ids)!=task.own_assignment_fingerprint):return 'obsolete'
    return task.status

def scoped_task(db,account,task_id,*,lock=False,current=False):
    task=get_entity(db,TeamIdentityReviewTask,task_id,lock=lock);grant=require_captain_team(db,account,task.team_id)
    if lock:
        grant=db.scalar(select(TeamCaptainGrant).where(TeamCaptainGrant.id==grant.id,TeamCaptainGrant.active).with_for_update().execution_options(populate_existing=True))
        if grant is None:raise DomainError('not_found','Задание недоступно',status=404)
    if grant.id!=task.grant_id:raise DomainError('not_found','Задание недоступно',status=404)
    if current and task_status(db,task) not in ('open','needs_material_fix','team_confirmed'):
        raise DomainError('obsolete_task','Задание отозвано или устарело. Организатор должен выдать новое.',status=409)
    return task

def task_view(db,task):
    run=get_entity(db,AnalysisRun,task.run_id);job=get_entity(db,AnalysisJob,run.job_id);match=get_entity(db,Match,run.match_id)
    confirmation=db.scalar(select(TeamIdentityConfirmation).where(TeamIdentityConfirmation.task_id==task.id).order_by(TeamIdentityConfirmation.created_at.desc()).limit(1))
    status=task_status(db,task,run,job)
    return {'id':task.id,'run_id':run.id,'match_id':run.match_id,'team_id':task.team_id,'team_name':job.context['teams'][task.side]['name'],
        'opponent_name':job.context['teams']['away' if task.side=='home' else 'home']['name'],'scheduled_at':match.scheduled_at,
        'side':task.side,'status':status,'revision':task.revision,'expires_at':task.expires_at,'can_correct':run.status=='review' and status=='team_confirmed',
        'reason':task.reason,'groups':task.groups,'players':task.players,'draft':task.draft,
        'confirmed_by_kind':confirmation.actor_kind if confirmation else None,'confirmation_id':confirmation.id if confirmation else None,'confirmation_version':confirmation.version if confirmation else None}
