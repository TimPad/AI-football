from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, Request, UploadFile, File, Header
from fastapi.responses import Response
from sqlalchemy.orm import Session
from aifootball.service.db import get_session
from aifootball.service.auth.security import require_admin, require_analytics_admin
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.analysis.models import AnalysisJob, AnalysisRun
from aifootball.service.analysis.schemas import JobCreate, JobView, AssignmentsUpdate, PointerMutation, RunView, Overview, PlayerHistoryView, PublicAnalysis
from aifootball.service.analysis.jobs import create_job, export_job
from aifootball.service.analysis.queries import match_analysis, run_view, get_player_history, get_public_analysis
from aifootball.service.analysis.commands import mutate
from aifootball.service.analysis.storage import limits, read_upload, read_file
from aifootball.service.analysis.imports import import_result
from aifootball.analytics.exchange import validate_result, ExchangeError

router = APIRouter()


@router.post('/matches/{mid}/analysis/jobs', response_model=JobView)
def job(mid: UUID, data: JobCreate, admin=Depends(require_analytics_admin), db: Session=Depends(get_session)):
    with db.begin():
        return create_job(db, mid, admin.id, data.request_id)


@router.get('/matches/{mid}/analysis/jobs/{jid}/package', dependencies=[Depends(require_admin)])
def package(mid: UUID, jid: UUID, db: Session=Depends(get_session)):
    job = get_entity(db, AnalysisJob, jid)
    if job.match_id != mid:
        raise DomainError('not_found', 'Задание не найдено', status=404)
    return Response(export_job(job), media_type='application/zip', headers={
        'Content-Disposition': f'attachment; filename="job-{jid}.zip"', 'Cache-Control': 'private, no-store'})


@router.post('/matches/{mid}/analysis/imports', response_model=RunView)
def upload(mid: UUID, request: Request, file: UploadFile=File(), request_id: UUID=Header(alias='X-Request-ID'),
           admin=Depends(require_analytics_admin), db: Session=Depends(get_session)):
    settings = request.app.state.settings
    try:
        result = validate_result(read_upload(file.file, settings), limits(settings))
    except ExchangeError as exc:
        raise DomainError('analysis_package', str(exc)) from exc
    created = []
    with db.begin():
        try:
            return import_result(db, mid, admin.id, request_id, result, settings.attachment_root, created)
        except Exception:
            for path in created: path.unlink(missing_ok=True)
            raise


@router.get('/matches/{mid}/analysis', response_model=Overview, dependencies=[Depends(require_admin)])
def overview(mid: UUID, db: Session=Depends(get_session)):
    return match_analysis(db, mid)


def scoped_run(db, mid, rid, *, lock=False):
    run = get_entity(db, AnalysisRun, rid, lock=lock)
    if run.match_id != mid: raise DomainError('not_found', 'Отчёт не найден', status=404)
    return run


@router.get('/matches/{mid}/analysis/runs/{rid}', response_model=RunView, dependencies=[Depends(require_admin)])
def detail(mid: UUID, rid: UUID, db: Session=Depends(get_session)):
    return run_view(db, scoped_run(db, mid, rid))


@router.get('/matches/{mid}/analysis/runs/{rid}/thumbs/{tid}', dependencies=[Depends(require_admin)])
def thumbnail(mid: UUID, rid: UUID, tid: int, request: Request, db: Session=Depends(get_session)):
    run = scoped_run(db, mid, rid)
    track = next((t for t in run.tracks['tracks'] if t['track_id'] == tid), None)
    if not track or not track.get('thumb'): raise DomainError('not_found', 'Миниатюра не найдена', status=404)
    return Response(read_file(request.app.state.settings.attachment_root, run.storage_key, track['thumb']),
                    media_type='image/jpeg', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.put('/matches/{mid}/analysis/runs/{rid}/assignments', response_model=RunView)
def assign(mid: UUID, rid: UUID, data: AssignmentsUpdate, admin=Depends(require_analytics_admin), db: Session=Depends(get_session)):
    with db.begin(): return mutate(db, mid, rid, admin.id, data, 'assignments')


@router.post('/matches/{mid}/analysis/runs/{rid}/{kind}', response_model=RunView)
def action(mid: UUID, rid: UUID, kind: Literal['confirm', 'activate', 'publish', 'reviews'], data: PointerMutation, admin=Depends(require_analytics_admin), db: Session=Depends(get_session)):
    if kind not in ('confirm', 'activate', 'publish', 'reviews'):
        raise DomainError('not_found', 'Команда не найдена', status=404)
    with db.begin(): return mutate(db, mid, rid, admin.id, data, kind)


@router.get('/players/{pid}/analysis', response_model=PlayerHistoryView, dependencies=[Depends(require_admin)])
def history(pid: UUID, db: Session=Depends(get_session)):
    return get_player_history(db, pid)


@router.get('/public/matches/{mid}/analysis', response_model=PublicAnalysis)
def public(mid: UUID, db: Session=Depends(get_session)):
    return get_public_analysis(db, mid)


from aifootball.service.analysis.schemas import UnderstandingView,UnderstandingReviewUpdate
from aifootball.service.analysis.understanding import get_understanding,review_understanding


@router.get('/matches/{mid}/analysis/runs/{rid}/understanding',response_model=UnderstandingView)
def understanding_detail(mid:UUID,rid:UUID,admin=Depends(require_analytics_admin),db:Session=Depends(get_session)):
    return get_understanding(db,scoped_run(db,mid,rid))


@router.get('/matches/{mid}/analysis/runs/{rid}/understanding/evidence/{eid}')
def understanding_evidence(mid:UUID,rid:UUID,eid:str,request:Request,admin=Depends(require_analytics_admin),db:Session=Depends(get_session)):
    run=scoped_run(db,mid,rid)
    evidence=next((item for item in (run.understanding or {}).get('evidence',[]) if item['id']==eid),None)
    if evidence is None:raise DomainError('not_found','Доказательство не найдено',status=404)
    return Response(read_file(request.app.state.settings.attachment_root,run.storage_key,evidence['path']),
        media_type='image/jpeg',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@router.put('/matches/{mid}/analysis/runs/{rid}/understanding/reviews',response_model=UnderstandingView)
def understanding_review(mid:UUID,rid:UUID,data:UnderstandingReviewUpdate,admin=Depends(require_analytics_admin),db:Session=Depends(get_session)):
    with db.begin():return review_understanding(db,mid,rid,admin.id,data)
