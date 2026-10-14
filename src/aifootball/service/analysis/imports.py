from uuid import UUID
from sqlalchemy import select
from aifootball.analytics.exchange import ValidatedResult
from aifootball.service.analysis.models import AnalysisJob, AnalysisRun
from aifootball.service.analysis.jobs import prior_command, remember
from aifootball.service.analysis.context import build_context, context_hash
from aifootball.service.analysis.queries import run_view
from aifootball.service.analysis.storage import put_package
from aifootball.service.halls.operations import lock_request
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError


def import_result(db, match_id, actor_id, request_id, result, root, created_paths):
    prior, hashed = prior_command(db, match_id, actor_id, request_id, 'import', {'hash': result.content_hash})
    if prior:
        return prior.response
    manifest = result.manifest
    if manifest['match_id'] != str(match_id):
        raise DomainError('foreign_match', 'Результат относится к другому матчу')
    lock_request(db, UUID(manifest['run_id']))
    current = build_context(db, match_id)
    job = get_entity(db, AnalysisJob, UUID(manifest['job_id']))
    if job.match_id != match_id or manifest['context_hash'] != job.context_hash or context_hash(current) != job.context_hash:
        raise DomainError('analysis_context', 'Состав или камера изменились. Создайте новое задание.')
    camera = job.context['camera']; pitch = result.report['pitch']; source = manifest['source_video']
    if manifest['camera_profile_id'] != camera['id'] or source['width'] != camera['frame_width'] or source['height'] != camera['frame_height'] or any(pitch[k] != job.context['pitch'][k] for k in ['length_m', 'width_m']):
        raise DomainError('analysis_geometry', 'Разрешение и геометрия отчёта не совпадают с заданием')
    by_id = db.get(AnalysisRun, UUID(manifest['run_id']))
    if by_id and (by_id.job_id != job.id or by_id.content_hash != result.content_hash):
        raise DomainError('run_conflict', 'UUID прогона уже используется другим результатом', status=409)
    run = db.scalar(select(AnalysisRun).where(AnalysisRun.job_id == job.id,
                                            AnalysisRun.content_hash == result.content_hash, AnalysisRun.source_run_id.is_(None)))
    if run is None:
        key, created = put_package(root, result)
        if created: created_paths.append(created)
        run = AnalysisRun(id=UUID(manifest['run_id']), job_id=job.id, match_id=match_id, created_by=actor_id,
                          content_hash=result.content_hash, storage_key=key, manifest=manifest,
                          report=result.report, tracks=result.tracks, checks=result.checks)
        db.add(run); db.flush()
    return remember(db, match_id, actor_id, request_id, hashed, run_view(db, run))
