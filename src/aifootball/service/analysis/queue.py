"""A paginated tournament work queue. No per-match database reads or processor guesses."""
from collections import defaultdict
from types import SimpleNamespace
from uuid import UUID
from datetime import datetime
from typing import Literal
from pydantic import BaseModel,Field
from sqlalchemy import select,func,case,cast,String,Integer,or_,literal
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased
from aifootball.service.common import get_entity
from aifootball.service.db import utcnow
from aifootball.service.tournaments.models import Tournament
from aifootball.service.catalog.models import Entry,Team
from aifootball.service.matches.models import Match,LineupMember
from aifootball.service.halls.models import CameraProfile
from aifootball.service.captains.models import TeamCaptainGrant
from aifootball.service.analysis.models import AnalysisJob,AnalysisRun,AnalysisAssignment
from aifootball.service.analysis.context import context_hash
from aifootball.service.analysis.team_review.models import TeamIdentityReviewTask,TeamIdentityConfirmation
from aifootball.service.analysis.team_review.queries import side_material
from aifootball.service.analysis.team_review.schemas import TeamSideStatus
from aifootball.service.errors import DomainError

QueueStage=Literal['not_started','awaiting_result','stale','quality_blocked','review','unpublished','published']
class QueueAction(BaseModel):
    label:str
    href:str
class AnalysisQueueItem(BaseModel):
    match_id:UUID
    home_name:str
    away_name:str
    scheduled_at:datetime
    job_id:UUID|None=None
    run_id:UUID|None=None
    published_run_id:UUID|None=None
    status:QueueStage
    unresolved:int=0
    context_stale:bool=False
    reason:str
    teams:list[TeamSideStatus]=Field(default_factory=list)
    next_action:QueueAction

def queue_query(tid):
    jobs=select(AnalysisJob.id,AnalysisJob.match_id,AnalysisJob.context,AnalysisJob.context_hash,
        func.row_number().over(partition_by=AnalysisJob.match_id,order_by=(AnalysisJob.created_at.desc(),AnalysisJob.id.desc())).label('rank')).join(Match,Match.id==AnalysisJob.match_id).where(Match.tournament_id==tid).cte('ranked_jobs')
    j=select(jobs).where(jobs.c.rank==1).cte('latest_jobs')
    ranked=select(AnalysisRun.id,AnalysisRun.job_id,AnalysisRun.status,AnalysisRun.tracks,AnalysisRun.side_map,AnalysisRun.identity_workflow,AnalysisRun.side_map_verified,
        AnalysisRun.checks['passed'].as_boolean().label('passed'),AnalysisRun.checks['critical_errors'].label('critical_errors'),
        func.row_number().over(partition_by=AnalysisRun.job_id,order_by=(AnalysisRun.created_at.desc(),AnalysisRun.id.desc())).label('rank')).join(j,AnalysisRun.job_id==j.c.id).cte('ranked_runs')
    r=select(ranked).where(ranked.c.rank==1).cte('latest_runs')
    he,ae=aliased(Entry),aliased(Entry);ht,at=aliased(Team),aliased(Team);camera=CameraProfile
    base=select(Match.id.label('match_id'),Match.scheduled_at,Match.camera_profile_id,Match.published_analysis_run_id.label('published_run_id'),
        ht.name.label('home_name'),at.name.label('away_name'),j.c.id.label('job_id'),j.c.context,j.c.context_hash,
        r.c.id.label('run_id'),r.c.status.label('run_status'),r.c.tracks,r.c.side_map,r.c.identity_workflow)
    base=base.select_from(Match).join(he,Match.home_entry_id==he.id).join(ae,Match.away_entry_id==ae.id).join(ht,he.team_id==ht.id).join(at,ae.team_id==at.id).outerjoin(j,j.c.match_id==Match.id).outerjoin(r,r.c.job_id==j.c.id).outerjoin(camera,Match.camera_profile_id==camera.id).where(Match.tournament_id==tid)
    roster_doc=func.jsonb_build_array(func.jsonb_build_object('player_id',cast(LineupMember.player_id,String),'side',LineupMember.side,'display_name',LineupMember.display_name,'shirt_number',LineupMember.shirt_number))
    roster_diff=select(literal(1)).where(LineupMember.match_id==Match.id,~j.c.context['rosters'].contains(roster_doc)).correlate(Match,j).exists()
    roster_count=select(func.count()).select_from(LineupMember).where(LineupMember.match_id==Match.id).correlate(Match).scalar_subquery()
    current_camera=func.jsonb_build_object('id',cast(camera.id,String),'version',camera.version,'frame_width',camera.frame_width,'frame_height',camera.frame_height,
        'homography',camera.homography,'polygon_px',camera.pitch_polygon_px,'calibration',camera.calibration).op('||')(case((camera.reference_sha256.is_not(None),func.jsonb_build_object('reference_sha256',camera.reference_sha256)),else_=cast(literal('{}'),JSONB)))
    current_pitch=func.jsonb_build_object('length_m',camera.pitch_length_m,'width_m',camera.pitch_width_m)
    current_teams=func.jsonb_build_object('home',func.jsonb_build_object('id',cast(ht.id,String),'name',ht.name),'away',func.jsonb_build_object('id',cast(at.id,String),'name',at.name))
    stale=func.coalesce(or_(camera.id.is_(None),camera.hall_id!=Match.hall_id,j.c.context['hall_id'].as_string()!=cast(Match.hall_id,String),
        j.c.context['camera']!=current_camera,j.c.context['pitch']!=current_pitch,j.c.context['teams']!=current_teams,
        func.jsonb_array_length(j.c.context['rosters'])!=roster_count,roster_diff,
        func.abs(camera.pitch_length_m-Match.hall_snapshot['pitch_length_m'].as_float())>0.000001,
        func.abs(camera.pitch_width_m-Match.hall_snapshot['pitch_width_m'].as_float())>0.000001),False)
    elements=func.jsonb_array_elements(func.coalesce(r.c.tracks['tracks'],cast(literal('[]'),JSONB))).table_valued('value').alias('queue_track')
    track=cast(elements.c.value,JSONB)
    resolved=select(literal(1)).where(AnalysisAssignment.run_id==r.c.id,AnalysisAssignment.track_id==cast(track['track_id'].as_string(),Integer)).correlate(r,elements).exists()
    unresolved=select(func.count()).select_from(elements).where(track['role'].as_string().in_(['player','goalkeeper']),~resolved).correlate(r).scalar_subquery()
    stage=case((j.c.id.is_(None),'not_started'),(r.c.id.is_(None),'awaiting_result'),(stale,'stale'),
        (or_(~r.c.passed,func.jsonb_array_length(r.c.critical_errors)>0),'quality_blocked'),(r.c.status=='review','review'),
        (r.c.id.is_distinct_from(Match.published_analysis_run_id),'unpublished'),else_='published')
    return base.add_columns(stage.label('status'),stale.label('context_stale'),unresolved.label('unresolved')).subquery('queue')

def own_digest(assignments,ids):
    return context_hash([{'track_id':a.track_id,'player_id':str(a.player_id) if a.player_id else None,'excluded_reason':a.excluded_reason} for a in sorted(assignments,key=lambda a:a.track_id) if a.track_id in ids])

def batched_sides(db,rows):
    ids=[row['run_id'] for row in rows if row['run_id']];out={}
    if not ids:return out
    assigned=defaultdict(list);confirmations=defaultdict(list);tasks=defaultdict(list)
    for a in db.scalars(select(AnalysisAssignment).where(AnalysisAssignment.run_id.in_(ids))):assigned[a.run_id].append(a)
    for c in db.scalars(select(TeamIdentityConfirmation).where(TeamIdentityConfirmation.run_id.in_(ids)).order_by(TeamIdentityConfirmation.version.desc())):confirmations[c.run_id].append(c)
    for task,active in db.execute(select(TeamIdentityReviewTask,TeamCaptainGrant.active).join(TeamCaptainGrant,TeamCaptainGrant.id==TeamIdentityReviewTask.grant_id).where(TeamIdentityReviewTask.run_id.in_(ids)).order_by(TeamIdentityReviewTask.created_at.desc())):tasks[task.run_id].append((task,active))
    for row in rows:
        rid=row['run_id']
        if not rid:continue
        if row['identity_workflow']=='admin' and not confirmations[rid] and not tasks[rid]:
            out[rid]=[];continue
        run=SimpleNamespace(tracks=row['tracks'],side_map=row['side_map']);job=SimpleNamespace(context=row['context']);sides=[]
        for side in ('home','away'):
            last=next((c for c in confirmations[rid] if c.side==side),None);opened=next(((t,active) for t,active in tasks[rid] if t.side==side and t.status in ('open','needs_material_fix')),None)
            status='not_issued';fingerprint=None;digest=None
            try:
                tracks,_,_,fingerprint=side_material(run,job,side);digest=own_digest(assigned[rid],set(tracks))
                valid=bool(last and not row['context_stale'] and last.context_hash==row['context_hash'] and last.group_fingerprint==fingerprint and last.assignment_fingerprint==digest)
                status='team_confirmed' if valid else 'obsolete' if last else 'not_issued'
            except DomainError:status='obsolete'
            if opened:
                task,active=opened
                status=task.status if active and not row['context_stale'] and task.expires_at>utcnow() and task.group_fingerprint==fingerprint and task.own_assignment_fingerprint==digest else 'obsolete'
            sides.append({'side':side,'status':status,'actor_kind':last.actor_kind if last else None,'actor_id':last.actor_id if last else None,'version':last.version if last else None,'confirmation_id':last.id if last else None,'reason':last.reason if last else ''})
        out[rid]=sides
    return out

def analysis_queue(db,tid,status,offset,limit):
    get_entity(db,Tournament,tid);q=queue_query(tid);where=[q.c.status==status] if status else []
    total=db.scalar(select(func.count()).select_from(q).where(*where))
    rows=db.execute(select(q).where(*where).order_by(q.c.scheduled_at,q.c.match_id).offset(offset).limit(limit)).mappings().all()
    sides=batched_sides(db,rows);items=[]
    reasons={'not_started':'Задание обработки ещё не создано','awaiting_result':'Задание создано. Результат ещё не загружен','stale':'Состав или камера изменились. Нужны новое задание и результат','quality_blocked':'Критические проверки результата не пройдены','review':'Проверьте личности игроков и качество результата','unpublished':'Версия подтверждена и ещё не опубликована','published':'Текущая подтверждённая версия на сайте'}
    for row in rows:
        stage=row['status'];mid=row['match_id'];rid=row['run_id'];teams=sides.get(rid,[])
        tab='publication' if stage=='unpublished' else 'review';label={'not_started':'Создать задание','awaiting_result':'Загрузить результат','stale':'Создать новое задание','quality_blocked':'Проверить результат','review':'Проверить игроков','unpublished':'Опубликовать видеоанализ','published':'Открыть опубликованную версию'}[stage]
        if stage=='not_started' and not row['camera_profile_id']:tab='info';label='Настроить камеру'
        if stage=='review' and row['identity_workflow']=='team' and teams and all(s['status']=='team_confirmed' for s in teams):label='Технически подтвердить'
        items.append({k:row[k] for k in ('match_id','home_name','away_name','scheduled_at','job_id','run_id','published_run_id','status','unresolved','context_stale')}|{'reason':reasons[stage],'teams':teams,'next_action':{'label':label,'href':f'/matches/{mid}?tab={tab}'+(f'&run_id={rid}' if rid else '')}})
    return {'items':items,'total':total}
