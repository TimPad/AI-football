from uuid import UUID
from sqlalchemy import select
from fastapi.encoders import jsonable_encoder
from aifootball.service.common import get_entity
from aifootball.service.matches.models import Match
from aifootball.service.analysis.models import AnalysisJob, AnalysisRun, AnalysisAssignment, PlayerMatchMetric


def job_view(job):
    return {'id': job.id, 'match_id': job.match_id, 'created_at': job.created_at,
            'context_hash': job.context_hash, 'context': job.context}


def run_summary(run):
    files = run.manifest.get('files', {})
    return {'has_understanding': 'understanding.json' in files, 'has_events': 'events.json' in files, 'id': run.id, 'job_id': run.job_id, 'created_at': run.created_at, 'status': run.status,
            'revision': run.revision, 'source_run_id': run.source_run_id,
            'partial': run.checks['partial'], 'passed': run.checks['passed']}


def run_view(db, run):
    job = get_entity(db, AnalysisJob, run.job_id)
    match = get_entity(db, Match, run.match_id)
    assigned = db.scalars(select(AnalysisAssignment).where(AnalysisAssignment.run_id == run.id).order_by(AnalysisAssignment.track_id)).all()
    metrics = db.scalars(select(PlayerMatchMetric).where(PlayerMatchMetric.run_id == run.id).order_by(PlayerMatchMetric.side, PlayerMatchMetric.player_id)).all()
    return jsonable_encoder({**run_summary(run), 'match_id': run.match_id, 'manifest': run.manifest,
                             'analysis_revision': match.analysis_revision, 'active_run_id': match.active_analysis_run_id,
                             'published_run_id': match.published_analysis_run_id,
                             'report': run.report, 'tracks': run.tracks['tracks'], 'checks': run.checks,
                             'context': job.context, 'side_map': run.side_map,
                             'assignments': [{'track_id': a.track_id, 'player_id': a.player_id,
                                              'excluded_reason': a.excluded_reason} for a in assigned],
                             'players': [metric_view(m) for m in metrics]})


def metric_view(metric):
    return {'player_id': metric.player_id, 'display_name': metric.display_name, 'shirt_number': metric.shirt_number,
            'side': metric.side, 'track_ids': metric.track_ids, 'metrics': metric.metrics}


def match_analysis(db, match_id):
    match = get_entity(db, Match, match_id)
    return {'match_id': match_id, 'analysis_revision': match.analysis_revision,
            'active_run_id': match.active_analysis_run_id, 'published_run_id': match.published_analysis_run_id,
            'jobs': [job_view(job) for job in db.scalars(select(AnalysisJob).where(AnalysisJob.match_id == match_id).order_by(AnalysisJob.created_at.desc(), AnalysisJob.id))],
            'runs': [run_summary(run) for run in db.scalars(select(AnalysisRun).where(AnalysisRun.match_id == match_id).order_by(AnalysisRun.created_at.desc(), AnalysisRun.id))]}


def get_player_history(db, player_id):
    from aifootball.service.catalog.models import Player
    from aifootball.service.analysis.aggregation import aggregate_player
    get_entity(db, Player, player_id)
    rows = db.execute(select(PlayerMatchMetric, Match, AnalysisRun).join(Match, Match.id == PlayerMatchMetric.match_id)
                      .join(AnalysisRun, AnalysisRun.id == PlayerMatchMetric.run_id)
                      .where(PlayerMatchMetric.player_id == player_id, Match.active_analysis_run_id == PlayerMatchMetric.run_id)
                      .order_by(Match.scheduled_at.desc(), Match.id)).all()
    matches = []
    for metric, match, run in rows:
        job = get_entity(db, AnalysisJob, run.job_id)
        matches.append({'match_id': match.id, 'run_id': run.id, 'scheduled_at': match.scheduled_at,
                        'teams': job.context['teams'], 'pitch': run.report['pitch'],
                        'partial': run.checks['partial'], **metric_view(metric)})
    # Do not sum heatmaps from different venues across matches.
    total = aggregate_player([{**metric.metrics, 'heatmap_s': None} for metric, _, _ in rows])
    return {'player_id': player_id, 'match_count': len(matches), 'totals': total, 'matches': matches}


def get_public_analysis(db, match_id):
    from aifootball.service.errors import DomainError
    match = get_entity(db, Match, match_id)
    if not match.published_analysis_run_id: raise DomainError('not_found', 'Аналитика ещё не опубликована', status=404)
    run = get_entity(db, AnalysisRun, match.published_analysis_run_id)
    job = get_entity(db, AnalysisJob, run.job_id)
    rows = db.scalars(select(PlayerMatchMetric).where(PlayerMatchMetric.run_id == run.id)
                      .order_by(PlayerMatchMetric.side, PlayerMatchMetric.player_id)).all()
    players = []
    for row in rows:
        values = {key: row.metrics.get(key) for key in ['distance_m', 'observed_s', 'm_per_min', 'hsr_m', 'sprints', 'vmax_ms', 'heatmap_s']}
        players.append({'player_id': row.player_id, 'display_name': row.display_name,
                        'shirt_number': row.shirt_number, 'side': row.side, 'metrics': values})
    periods = []
    for p in run.report['periods']:
        teams = {side: {key: values.get(key) for key in ['distance_m', 'observed_s', 'm_per_min', 'hsr_m', 'sprints', 'heatmap_s', 'width_m', 'depth_m', 'compactness_m2']}
                 for side, values in p.get('teams', {}).items() if side in ('A', 'B')}
        for side, values in teams.items():
            source = p['teams'][side]
            values['low_data'] = bool(source.get('low_data', False))
            values['metric_notes'] = {key: ('Нет наблюдений команды' if not source.get('observed_s') else 'Недостаточно данных') for key, value in values.items() if value is None}
        # Трети — только три целых процента (своя/средняя/чужая) или None, без служебных полей отчёта.
        thirds = {side: (list(v) if isinstance(v, list) and len(v) == 3 and all(isinstance(x, int) and 0 <= x <= 100 for x in v) else None)
                  for side, v in (p.get('thirds') or {}).items() if side in ('A', 'B')}
        periods.append({'key': p['key'], 'name': p['name'], 'duration_s': p['duration_s'], 'teams': teams, 'thirds': thirds})
    pitch = {key: run.report['pitch'][key] for key in ('length_m','width_m','cell_m')}
    pitch['orientation'] = run.report['pitch'].get('orientation', 'camera')
    return {'match_id': match_id, 'run_id': run.id, 'pitch': pitch, 'teams': job.context['teams'],
            'side_map': run.side_map, 'primary_period_key': run.manifest['primary_period_key'],
            'video_s': run.manifest['source_video']['duration_s'], 'processed_s': run.report['match']['processed_s'],
            'partial': run.checks['partial'], 'periods': periods, 'players': players}
