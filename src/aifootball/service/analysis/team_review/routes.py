from datetime import timedelta
from uuid import UUID
from fastapi import APIRouter,Depends,Request,Query
from fastapi.responses import Response
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from aifootball.service.db import get_session,utcnow
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.auth.security import require_analytics_admin,require_analytics_reader
from aifootball.service.captains.security import require_captain,require_captain_csrf
from aifootball.service.captains.commands import command as captain_command
from aifootball.service.captains.models import TeamCaptainGrant
from aifootball.service.matches.models import Match
from aifootball.service.analysis.models import AnalysisRun,AnalysisJob
from aifootball.service.analysis.jobs import prior_command,remember
from aifootball.service.analysis.context import build_context,context_hash
from aifootball.service.analysis.storage import read_file
from .models import TeamIdentityReviewTask
from .schemas import TeamTaskCreate,TeamTaskView,TeamTaskList,TeamTaskDraft,TeamTaskCommand,AdminSideConfirmation,TeamSideStatuses
from .queries import side_material,assignment_fingerprint,task_status,task_view,scoped_task,latest_run_id
from .confirmations import save_draft,confirm_team,corrections,admin_confirm_side,side_statuses

router=APIRouter()

@router.get('/matches/{mid}/analysis/runs/{rid}/team-confirmations',response_model=TeamSideStatuses)
def admin_side_status(mid:UUID,rid:UUID,admin=Depends(require_analytics_reader),db:Session=Depends(get_session)):
    run=get_entity(db,AnalysisRun,rid)
    if run.match_id!=mid:raise DomainError('not_found','Отчёт не найден',status=404)
    return side_statuses(db,run)

@router.post('/matches/{mid}/analysis/runs/{rid}/team-confirmations',response_model=TeamSideStatuses)
def admin_side_confirm(mid:UUID,rid:UUID,data:AdminSideConfirmation,admin=Depends(require_analytics_admin),db:Session=Depends(get_session)):
    with db.begin():
        prior,digest=prior_command(db,mid,admin.id,data.request_id,'admin_side_confirmation',{'run_id':str(rid),**data.model_dump(mode='json',exclude={'request_id'})})
        if prior:return prior.response
        result=admin_confirm_side(db,mid,rid,admin.id,data)
        return remember(db,mid,admin.id,data.request_id,digest,result)

def captain_mutation(db,captain,task_id,data,kind,execute):
    scoped_task(db,captain,task_id,current=True)  # Recheck current access before even replaying a committed command.
    return captain_command(db,captain.id,data.request_id,'identity_'+kind,{'task_id':str(task_id),**data.model_dump(mode='json',exclude={'request_id'})},lambda:execute(db,captain,task_id,data))

@router.put('/captain/identity-tasks/{task_id}/draft',response_model=TeamTaskView)
def captain_draft(task_id:UUID,data:TeamTaskDraft,captain=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    with db.begin():return captain_mutation(db,captain,task_id,data,'draft',save_draft)

@router.post('/captain/identity-tasks/{task_id}/confirm',response_model=TeamTaskView)
def captain_confirm(task_id:UUID,data:TeamTaskCommand,captain=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    with db.begin():return captain_mutation(db,captain,task_id,data,'confirm',confirm_team)

@router.post('/captain/identity-tasks/{task_id}/corrections',response_model=TeamTaskView)
def captain_corrections(task_id:UUID,data:TeamTaskCommand,captain=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    with db.begin():return captain_mutation(db,captain,task_id,data,'corrections',corrections)

@router.post('/matches/{mid}/analysis/runs/{rid}/team-review-tasks',response_model=TeamTaskView,status_code=201)
def create_task(mid:UUID,rid:UUID,data:TeamTaskCreate,admin=Depends(require_analytics_admin),db:Session=Depends(get_session)):
    with db.begin():
        prior,digest=prior_command(db,mid,admin.id,data.request_id,'team_task',{'run_id':str(rid),**data.model_dump(mode='json',exclude={'request_id'})})
        if prior:return prior.response
        get_entity(db,Match,mid,lock=True);run=get_entity(db,AnalysisRun,rid,lock=True)
        if run.match_id!=mid:raise DomainError('not_found','Отчёт не найден',status=404)
        if run.revision!=data.expected_run_revision:raise DomainError('revision_conflict','Проверка изменилась. Обновите страницу.',status=409)
        if latest_run_id(db,mid)!=run.id:raise DomainError('obsolete_run','Есть новый результат. Выдайте задание из актуальной версии.',status=409)
        if run.status!='review':raise DomainError('immutable_analysis','Создайте новую версию проверки',status=409)
        if not run.side_map_verified:raise DomainError('sides_unverified','Сначала подтвердите соответствие команд A/B',status=409)
        job=get_entity(db,AnalysisJob,run.job_id)
        if context_hash(build_context(db,mid))!=job.context_hash:raise DomainError('analysis_context','Состав или камера изменились. Нужно новое задание обработки.',status=409)
        side=next((s for s,t in job.context['teams'].items() if str(t['id'])==str(data.team_id)),None)
        if side is None:raise DomainError('not_found','Команда не участвует в этом задании',status=404)
        grant=db.scalar(select(TeamCaptainGrant).where(TeamCaptainGrant.team_id==data.team_id,TeamCaptainGrant.active))
        if not grant:raise DomainError('captain_required','У команды нет действующего капитана. Пригласите его или подтвердите сторону сами с причиной.',status=409)
        old=db.scalars(select(TeamIdentityReviewTask).where(TeamIdentityReviewTask.run_id==rid,TeamIdentityReviewTask.side==side,TeamIdentityReviewTask.status.in_(['open','needs_material_fix']))).all()
        for task in old:
            if task_status(db,task,run,job) not in ('obsolete','revoked'):raise DomainError('task_open','У капитана уже есть открытое задание',status=409)
            task.status='obsolete';task.revision+=1
        db.flush()
        tracks,groups,players,fingerprint=side_material(run,job,side)
        if not tracks or not players:raise DomainError('material_missing','В результате нет фрагментов или игроков этой команды',status=409)
        task=TeamIdentityReviewTask(run_id=rid,team_id=data.team_id,grant_id=grant.id,side=side,created_by=admin.id,
            context_hash=job.context_hash,group_fingerprint=fingerprint,own_assignment_fingerprint=assignment_fingerprint(db,run,list(tracks)),
            allowed_track_ids=sorted(tracks),allowed_player_ids=[p['player_id'] for p in players],players=players,
            groups=[{'id':','.join(map(str,g)),'tracks':[{'track_id':i,'intervals':tracks[i]['intervals'],'has_thumbnail':bool(tracks[i].get('thumb'))} for i in g]} for g in groups],
            expires_at=utcnow()+timedelta(days=7))
        db.add(task);run.identity_workflow='team';run.revision+=1;db.flush()
        return remember(db,mid,admin.id,data.request_id,digest,task_view(db,task))

@router.get('/matches/{mid}/analysis/runs/{rid}/team-review-tasks',response_model=TeamTaskList)
def admin_tasks(mid:UUID,rid:UUID,admin=Depends(require_analytics_reader),db:Session=Depends(get_session)):
    run=get_entity(db,AnalysisRun,rid)
    if run.match_id!=mid:raise DomainError('not_found','Отчёт не найден',status=404)
    tasks=db.scalars(select(TeamIdentityReviewTask).where(TeamIdentityReviewTask.run_id==rid).order_by(TeamIdentityReviewTask.created_at.desc()).limit(100)).all()
    return {'items':[task_view(db,t) for t in tasks],'total':db.scalar(select(func.count()).select_from(TeamIdentityReviewTask).where(TeamIdentityReviewTask.run_id==rid))}

@router.get('/captain/identity-tasks',response_model=TeamTaskList)
def captain_tasks(limit:int=Query(default=25,ge=1,le=100),offset:int=Query(default=0,ge=0),captain=Depends(require_captain),db:Session=Depends(get_session)):
    query=select(TeamIdentityReviewTask).join(TeamCaptainGrant,TeamCaptainGrant.id==TeamIdentityReviewTask.grant_id).where(TeamCaptainGrant.account_id==captain.id,TeamCaptainGrant.active)
    tasks=db.scalars(query.order_by(TeamIdentityReviewTask.created_at.desc(),TeamIdentityReviewTask.id).offset(offset).limit(limit)).all()
    return {'items':[task_view(db,t) for t in tasks],'total':db.scalar(select(func.count()).select_from(query.subquery()))}

@router.get('/captain/identity-tasks/{task_id}',response_model=TeamTaskView)
def captain_task(task_id:UUID,response:Response,captain=Depends(require_captain),db:Session=Depends(get_session)):
    response.headers['Cache-Control']='private, no-store'
    return task_view(db,scoped_task(db,captain,task_id))

@router.get('/captain/identity-tasks/{task_id}/tracks/{track_id}/thumbnail')
def captain_thumbnail(task_id:UUID,track_id:int,request:Request,captain=Depends(require_captain),db:Session=Depends(get_session)):
    task=scoped_task(db,captain,task_id,current=True)
    if track_id not in task.allowed_track_ids:raise DomainError('not_found','Кадр недоступен',status=404)
    run=get_entity(db,AnalysisRun,task.run_id)
    track=next((t for t in run.tracks['tracks'] if t['track_id']==track_id),None)
    if not track or not track.get('thumb'):raise DomainError('not_found','Миниатюра отсутствует',status=404)
    return Response(read_file(request.app.state.settings.attachment_root,run.storage_key,track['thumb']),media_type='image/jpeg',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
