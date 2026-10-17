from uuid import UUID
from collections import defaultdict
from types import SimpleNamespace
from sqlalchemy import select,func
from aifootball.analytics.track_groups import OVERLAP_S
from aifootball.service.common import get_entity
from aifootball.service.db import utcnow
from aifootball.service.errors import DomainError
from aifootball.service.matches.models import Match
from aifootball.service.analysis.models import AnalysisRun,AnalysisJob,AnalysisAssignment
from aifootball.service.analysis.context import context_hash,build_context
from aifootball.service.analysis.assignments import set_assignments
from aifootball.service.analysis.schemas import AssignmentInput
from .models import TeamIdentityReviewTask,TeamIdentityConfirmation
from .queries import scoped_task,task_status,side_material,assignment_fingerprint,task_view

def lock_task(db,account,task_id,revision):
    task=scoped_task(db,account,task_id)
    get_entity(db,Match,get_entity(db,AnalysisRun,task.run_id).match_id,lock=True)
    run=get_entity(db,AnalysisRun,task.run_id,lock=True)
    task=scoped_task(db,account,task_id,lock=True,current=True)
    if run.status!='review':raise DomainError('immutable_analysis','Версия уже подтверждена. Организатор должен создать новую проверку.',status=409)
    if task.revision!=revision:raise DomainError('revision_conflict','Черновик изменён. Сверьте сохранённые решения.',status=409,current_revision=task.revision)
    return task,run,get_entity(db,AnalysisJob,run.job_id)

def validate_decisions(task,decisions,*,complete=False):
    ids={g['id'] for g in task.groups};seen=set()
    for d in decisions:
        if d.group_id not in ids or d.group_id in seen:raise DomainError('group','Неизвестная или повторная группа')
        seen.add(d.group_id)
        if d.kind=='player':
            if str(d.player_id) not in task.allowed_player_ids or d.reason:raise DomainError('foreign_player','Выберите игрока из снимка своей команды')
        elif d.player_id is not None or not d.reason.strip():raise DomainError('identity_reason','Укажите причину неопределённости или ошибки материала')
        if complete and d.kind=='material_issue':raise DomainError('material_issue','Нужно исправить материал и выдать новое задание.',status=409)
    if complete and seen!=ids:raise DomainError('identity_incomplete','Для каждой группы выберите игрока или явно укажите неизвестного.',status=409)

def save_draft(db,account,task_id,data):
    task,run,job=lock_task(db,account,task_id,data.expected_revision)
    if task.status not in ('open','needs_material_fix'):raise DomainError('correction_required','Сначала откройте исправление подтверждения',status=409)
    validate_decisions(task,data.decisions)
    task.draft=[d.model_dump(mode='json') for d in data.decisions];task.status='needs_material_fix' if any(d.kind=='material_issue' for d in data.decisions) else 'open';task.revision+=1
    db.flush();return task_view(db,task)

def check_overlaps(run,assignments):
    tracks={t['track_id']:t for t in run.tracks['tracks']};by_person=defaultdict(list)
    for a in assignments:
        if a.player_id:by_person[a.player_id].extend(tracks[a.track_id]['intervals'])
    for intervals in by_person.values():
        end=-1
        for start,stop in sorted(intervals):
            if start<end-OVERLAP_S:raise DomainError('overlapping_identity','Игроку назначены пересекающиеся фрагменты. Сообщите об ошибке материала.')
            end=max(end,stop)

def record_confirmation(db,run,job,side,team_id,actor_kind,actor_id,reason,decisions,task=None):
    tracks,_,_,fingerprint=side_material(run,job,side)
    version=(db.scalar(select(func.max(TeamIdentityConfirmation.version)).where(TeamIdentityConfirmation.run_id==run.id,TeamIdentityConfirmation.side==side)) or 0)+1
    row=TeamIdentityConfirmation(run_id=run.id,team_id=team_id,side=side,version=version,task_id=task.id if task else None,
        actor_kind=actor_kind,actor_id=actor_id,reason=reason,context_hash=job.context_hash,group_fingerprint=fingerprint,
        assignment_fingerprint=assignment_fingerprint(db,run,list(tracks)),decisions=decisions)
    db.add(row);db.flush();return row

def confirm_team(db,account,task_id,data):
    from .schemas import TeamDecision
    task,run,job=lock_task(db,account,task_id,data.expected_revision)
    if task.status not in ('open','needs_material_fix'):raise DomainError('already_confirmed','Команда уже подтверждена. Для правки откройте исправление.',status=409)
    decisions=[TeamDecision.model_validate(d) for d in task.draft];validate_decisions(task,decisions,complete=True)
    groups={g['id']:g for g in task.groups};patch=[]
    for decision in decisions:
        for t in groups[decision.group_id]['tracks']:
            patch.append(AssignmentInput(track_id=t['track_id'],player_id=decision.player_id,
                excluded_reason=('Не определён: '+decision.reason)[:500] if decision.kind=='unknown' else None))
    # Never replace the full run with a captain's partial list: re-read and merge under its lock.
    others=[AssignmentInput(track_id=a.track_id,player_id=a.player_id,excluded_reason=a.excluded_reason) for a in db.scalars(select(AnalysisAssignment).where(AnalysisAssignment.run_id==run.id)) if a.track_id not in task.allowed_track_ids]
    check_overlaps(run,patch)
    set_assignments(db,run,job,SimpleNamespace(side_map=run.side_map,assignments=others+patch));db.flush()
    record_confirmation(db,run,job,task.side,task.team_id,'captain',account.id,'Капитан самостоятельно подтвердил свою команду',task.draft,task)
    task.own_assignment_fingerprint=assignment_fingerprint(db,run,task.allowed_track_ids);task.status='team_confirmed';task.revision+=1;run.revision+=1
    db.flush();return task_view(db,task)

def corrections(db,account,task_id,data):
    task,run,job=lock_task(db,account,task_id,data.expected_revision)
    if task.status!='team_confirmed':raise DomainError('correction_required','Исправление открывается для подтверждённой команды',status=409)
    task.status='open';task.revision+=1;db.flush();return task_view(db,task)

def side_statuses(db,run,job=None):
    job=job or get_entity(db,AnalysisJob,run.job_id);sides=[]
    tasks=db.scalars(select(TeamIdentityReviewTask).where(TeamIdentityReviewTask.run_id==run.id).order_by(TeamIdentityReviewTask.created_at.desc())).all()
    confirmations=db.scalars(select(TeamIdentityConfirmation).where(TeamIdentityConfirmation.run_id==run.id).order_by(TeamIdentityConfirmation.version.desc())).all()
    for side in ('home','away'):
        task=next((t for t in tasks if t.side==side and t.status in ('open','needs_material_fix')),None)
        last=next((c for c in confirmations if c.side==side),None)
        valid=False
        try:
            tracks,_,_,fingerprint=side_material(run,job,side)
            valid=bool(last and last.context_hash==job.context_hash and last.group_fingerprint==fingerprint and last.assignment_fingerprint==assignment_fingerprint(db,run,list(tracks)))
        except DomainError:pass
        status=task_status(db,task,run,job) if task else 'team_confirmed' if valid else 'obsolete' if last else 'not_issued'
        sides.append({'side':side,'status':status,'actor_kind':last.actor_kind if last else None,'actor_id':last.actor_id if last else None,
            'version':last.version if last else None,'confirmation_id':last.id if last else None,'reason':last.reason if last else ''})
    return {'workflow':run.identity_workflow,'sides':sides}

def require_confirmed_sides(db,run,job):
    # Read source lineage too: an old review created before team workflow cannot bypass its ancestor.
    current=run;visited=set();team=False
    while current and current.id not in visited:
        visited.add(current.id);team=team or current.identity_workflow=='team'
        current=db.get(AnalysisRun,current.source_run_id) if current.source_run_id else None
    if not team:return
    statuses=side_statuses(db,run,job)['sides']
    open_task=db.scalar(select(TeamIdentityReviewTask.id).where(TeamIdentityReviewTask.run_id==run.id,TeamIdentityReviewTask.status.in_(['open','needs_material_fix'])).limit(1))
    if open_task or any(s['status']!='team_confirmed' for s in statuses):raise DomainError('teams_unconfirmed','Завершите подтверждение обеих команд или явно отзовите задания и подтвердите сторону с причиной.',status=409)

def admin_confirm_side(db,mid,rid,actor_id,data):
    get_entity(db,Match,mid,lock=True);run=get_entity(db,AnalysisRun,rid,lock=True)
    if run.match_id!=mid:raise DomainError('not_found','Отчёт не найден',status=404)
    if run.status!='review' or run.revision!=data.expected_run_revision:raise DomainError('revision_conflict','Версия изменилась или уже подтверждена',status=409)
    if not data.reason.strip():raise DomainError('reason','Укажите причину самостоятельной проверки')
    job=get_entity(db,AnalysisJob,run.job_id)
    if not run.side_map_verified or context_hash(build_context(db,mid))!=job.context_hash:raise DomainError('analysis_context','Проверьте стороны и актуальность задания обработки',status=409)
    tracks,_,_,_=side_material(run,job,data.side)
    rows=db.scalars(select(AnalysisAssignment).where(AnalysisAssignment.run_id==rid,AnalysisAssignment.track_id.in_(tracks))).all()
    if len(rows)!=len(tracks):raise DomainError('identity_incomplete','Назначьте все фрагменты стороны или явно исключите с причиной',status=409)
    check_overlaps(run,rows)
    for t in db.scalars(select(TeamIdentityReviewTask).where(TeamIdentityReviewTask.run_id==rid,TeamIdentityReviewTask.side==data.side,TeamIdentityReviewTask.status.in_(['open','needs_material_fix']))):
        t.status='revoked';t.reason=data.reason;t.revision+=1
    decisions=[{'track_id':a.track_id,'player_id':str(a.player_id) if a.player_id else None,'excluded_reason':a.excluded_reason} for a in rows]
    record_confirmation(db,run,job,data.side,UUID(job.context['teams'][data.side]['id']),'admin',actor_id,data.reason,decisions)
    run.identity_workflow='team';run.revision+=1;db.flush();return side_statuses(db,run,job)
