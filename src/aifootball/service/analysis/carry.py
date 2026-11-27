"""Одна разметка на матч: новая версия забирает решения прежней самой новой версии, если фрагменты те же.

Решения хранятся по номерам фрагментов, поэтому переносятся только при совпадении номеров, команд, ролей и отрезков.
Решения об игроках, которых нет в составе нового задания, остаются в прежней версии — о них пишет предупреждение.
"""

from sqlalchemy import select

from aifootball.service.analysis.models import AnalysisAssignment, AnalysisRun


def newest_run(db, match_id):
    return db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.match_id == match_id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .limit(1)
    )


def _key(track):
    return (
        track['track_id'],
        track.get('team'),
        track['role'],
        tuple((round(a, 3), round(b, 3)) for a, b in track['intervals']),
    )


def carry_labelling(db, run, previous, job):
    if previous is None:
        return
    rows = db.scalars(select(AnalysisAssignment).where(AnalysisAssignment.run_id == previous.id)).all()
    warnings = list(run.checks.get('warnings') or [])
    if sorted(map(_key, previous.tracks['tracks'])) != sorted(map(_key, run.tracks['tracks'])):
        if rows:
            note = 'Фрагменты отличаются от прежней версии — разметка не перенесена'
            run.checks = {**run.checks, 'warnings': [*warnings, note]}
        return
    roster = {p['player_id'] for p in job.context['rosters']}
    kept = [a for a in rows if a.player_id is None or str(a.player_id) in roster]
    for a in kept:
        db.add(
            AnalysisAssignment(
                run_id=run.id, track_id=a.track_id, player_id=a.player_id, excluded_reason=a.excluded_reason
            )
        )
    run.side_map = dict(previous.side_map)
    run.side_map_verified = previous.side_map_verified
    run.absent_players = [p for p in previous.absent_players or [] if p in roster]
    if rows:
        note = f'Перенесено решений из прежней версии: {len(kept)}'
        if len(kept) < len(rows):
            note += f'; не перенесено (игрок не в составе): {len(rows) - len(kept)}'
        run.checks = {**run.checks, 'warnings': [*warnings, note]}
