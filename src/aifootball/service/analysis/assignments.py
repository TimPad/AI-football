from collections import defaultdict
from uuid import UUID
from sqlalchemy import select, delete
from aifootball.service.analysis.models import AnalysisAssignment, PlayerMatchMetric
from aifootball.service.analysis.aggregation import aggregate_player
from aifootball.service.errors import DomainError


def set_assignments(db, run, job, data):
    if run.status != 'review':
        raise DomainError('immutable_analysis', 'Создайте новую версию проверки для изменения подтверждённых назначений', status=409)
    if set(data.side_map) != {'A', 'B'} or set(data.side_map.values()) != {'home', 'away'}:
        raise DomainError('sides', 'Стороны A и B должны соответствовать разным командам')
    tracks = {t['track_id']: t for t in run.tracks['tracks']}
    roster = {p['player_id']: p for p in job.context['rosters']}
    seen = set(); rows = []
    for item in data.assignments:
        if item.track_id not in tracks or item.track_id in seen:
            raise DomainError('track', 'Неизвестный или повторяющийся фрагмент')
        seen.add(item.track_id)
        if item.player_id and item.excluded_reason:
            raise DomainError('assignment', 'Фрагмент должен быть назначен игроку либо исключён')
        if item.player_id:
            player = roster.get(str(item.player_id)); track = tracks[item.track_id]
            if not player: raise DomainError('foreign_player', 'Игрок отсутствует в снимке состава задания')
            if track['role'] not in ('player', 'goalkeeper'):
                raise DomainError('role', 'Игроку нельзя назначить трек судьи или неизвестной роли')
            if track['team'] and player['side'] != data.side_map[track['team']]:
                raise DomainError('foreign_side', 'Игрок относится к другой стороне матча')
        if item.player_id or item.excluded_reason:
            rows.append(AnalysisAssignment(run_id=run.id, track_id=item.track_id,
                                            player_id=item.player_id, excluded_reason=item.excluded_reason))
    db.execute(delete(AnalysisAssignment).where(AnalysisAssignment.run_id == run.id))
    db.add_all(rows); run.side_map = data.side_map


def create_metrics(db, run, job):
    if not run.checks['passed'] or run.checks['critical_errors']:
        raise DomainError('analysis_quality', 'Критические проверки качества не пройдены. Исправьте источник и пересчитайте.')
    assigned = db.scalars(select(AnalysisAssignment).where(AnalysisAssignment.run_id == run.id,
                                                           AnalysisAssignment.player_id.is_not(None))).all()
    if not assigned: raise DomainError('identity_required', 'Подтвердите хотя бы одного игрока состава')
    tracks = {t['track_id']: t for t in run.tracks['tracks']}
    roster = {p['player_id']: p for p in job.context['rosters']}
    primary = next(p for p in run.report['periods'] if p['key'] == run.manifest['primary_period_key'])
    metrics = {p['track_id']: p for p in primary['players']}
    by_player = defaultdict(list)
    for assignment in assigned: by_player[assignment.player_id].append(assignment.track_id)
    rows = []
    for player_id, ids in by_player.items():
        observed = sorted((start, end, tid) for tid in ids for start, end in tracks[tid]['intervals'])
        previous_end = -1
        for start, end, tid in observed:
            if start < previous_end:
                raise DomainError('overlapping_identity', 'Одному игроку назначены пересекающиеся фрагменты. Исключите дубль или пересчитайте трек.')
            previous_end = end
        values = aggregate_player([metrics.get(tid, {}) for tid in ids])
        values['missing_track_ids'] = [tid for tid in ids if tid not in metrics]
        person = roster[str(player_id)]
        rows.append(PlayerMatchMetric(run_id=run.id, player_id=player_id, match_id=run.match_id,
                                      display_name=person['display_name'], shirt_number=person['shirt_number'],
                                      side=person['side'], track_ids=sorted(ids), metrics=values))
    db.add_all(rows)
