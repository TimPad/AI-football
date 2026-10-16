from uuid import uuid5, NAMESPACE_URL
from copy import deepcopy
from sqlalchemy import select
from aifootball.service.analysis.models import AnalysisRun, AnalysisJob, AnalysisAssignment
from aifootball.service.analysis.jobs import prior_command, remember
from aifootball.service.analysis.context import build_context, context_hash
from aifootball.service.analysis.assignments import set_assignments, create_metrics
from aifootball.service.analysis.queries import run_view
from aifootball.service.matches.models import Match
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError


def mutate(db, match_id, run_id, actor_id, data, kind):
    payload = {'run_id': str(run_id), **data.model_dump(mode='json', exclude={'request_id'})}
    prior, hashed = prior_command(db, match_id, actor_id, data.request_id, kind, payload)
    if prior: return prior.response
    match = get_entity(db, Match, match_id, lock=True)
    run = get_entity(db, AnalysisRun, run_id, lock=True)
    if run.match_id != match_id: raise DomainError('not_found', 'Отчёт не найден', status=404)
    if run.revision != data.expected_revision:
        raise DomainError('revision_conflict', 'Проверка аналитики изменена. Обновите версию и сверьте назначения.',
                          status=409, current_revision=run.revision)
    if kind in ('confirm', 'activate', 'publish') and match.analysis_revision != data.expected_analysis_revision:
        raise DomainError('analysis_version_conflict', 'Активная или опубликованная версия изменена. Обновите список версий.',
                          status=409, current_revision=match.analysis_revision)
    job = get_entity(db, AnalysisJob, run.job_id)
    if kind == 'assignments':
        set_assignments(db, run, job, data)
        run.side_map_verified = True
        run.revision += 1
    elif kind == 'confirm':
        if run.status != 'review': raise DomainError('already_confirmed', 'Эта версия уже подтверждена', status=409)
        if context_hash(build_context(db, match_id)) != job.context_hash:
            raise DomainError('analysis_context', 'Состав или камера изменились после импорта. Создайте новое задание.')
        create_metrics(db, run, job)
        run.status = 'confirmed'; run.confirmed_by = actor_id; run.revision += 1
        match.active_analysis_run_id = run.id; match.analysis_revision += 1
    elif kind in ('activate', 'publish'):
        if run.status != 'confirmed': raise DomainError('analysis_unconfirmed', 'Сначала подтвердите аналитику')
        if kind == 'activate': match.active_analysis_run_id = run.id
        else: match.published_analysis_run_id = run.id
        match.analysis_revision += 1; run.revision += 1
    elif kind == 'reviews':
        if run.status != 'confirmed': raise DomainError('analysis_unconfirmed', 'Новая проверка создаётся из подтверждённой версии')
        source = run
        run = AnalysisRun(id=uuid5(NAMESPACE_URL, f'aifootball:review:{match_id}:{data.request_id}'),
                          job_id=source.job_id, match_id=match_id, created_by=actor_id, source_run_id=source.id,
                          content_hash=source.content_hash, storage_key=source.storage_key, manifest=source.manifest,
                          report=source.report, tracks=source.tracks, checks=source.checks, side_map=source.side_map,
                          side_map_verified=source.side_map_verified, understanding=deepcopy(source.understanding),
                          events=deepcopy(source.events),
                          understanding_reviews=deepcopy(source.understanding_reviews))
        db.add(run); db.flush()
        for assignment in db.scalars(select(AnalysisAssignment).where(AnalysisAssignment.run_id == source.id)):
            db.add(AnalysisAssignment(run_id=run.id, track_id=assignment.track_id,
                                      player_id=assignment.player_id, excluded_reason=assignment.excluded_reason))
    db.flush()
    return remember(db, match_id, actor_id, data.request_id, hashed, run_view(db, run))
