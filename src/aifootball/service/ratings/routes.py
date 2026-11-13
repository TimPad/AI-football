from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from aifootball.service.auth.security import require_analytics_admin, require_analytics_reader
from aifootball.service.common import get_entity
from aifootball.service.db import get_session
from aifootball.service.errors import DomainError
from aifootball.service.matches.models import Match
from aifootball.service.ratings.actions import action_overview, action_view, save_actions
from aifootball.service.ratings.models import ActionVersion, ParticipationVersion
from aifootball.service.ratings.operations import participation_overview, participation_view, save_participation
from aifootball.service.ratings.schemas import (
    ActionsOverview,
    ActionsSave,
    ActionsView,
    ParticipationOverview,
    ParticipationSave,
    ParticipationView,
    TeamActionStats,
)
from aifootball.service.ratings.team_stats import private_action_stats, public_action_stats

router = APIRouter()


@router.get(
    '/matches/{mid}/participation',
    response_model=ParticipationOverview,
    dependencies=[Depends(require_analytics_reader)],
)
def participation(mid: UUID, db: Session = Depends(get_session)):
    return participation_overview(db, mid)


@router.get(
    '/matches/{mid}/participation/versions/{vid}',
    response_model=ParticipationView,
    dependencies=[Depends(require_analytics_reader)],
)
def version(mid: UUID, vid: UUID, db: Session = Depends(get_session)):
    value = get_entity(db, ParticipationVersion, vid)
    if value.match_id != mid:
        raise DomainError('not_found', 'Версия участия не найдена', status=404)
    return participation_view(value)


@router.put('/matches/{mid}/participation', response_model=ParticipationView)
def save(
    mid: UUID, data: ParticipationSave, actor=Depends(require_analytics_admin), db: Session = Depends(get_session)
):
    with db.begin():
        return save_participation(db, mid, actor.id, data)


@router.get(
    '/matches/{mid}/performance-actions',
    response_model=ActionsOverview,
    dependencies=[Depends(require_analytics_reader)],
)
def actions(mid: UUID, db: Session = Depends(get_session)):
    return action_overview(db, mid)


@router.get(
    '/matches/{mid}/performance-actions/versions/{vid}',
    response_model=ActionsView,
    dependencies=[Depends(require_analytics_reader)],
)
def actions_version(mid: UUID, vid: UUID, db: Session = Depends(get_session)):
    value = get_entity(db, ActionVersion, vid)
    if value.match_id != mid:
        raise DomainError('not_found', 'Версия действий не найдена', status=404)
    return action_view(value)


@router.put('/matches/{mid}/performance-actions', response_model=ActionsView)
def save_action_version(
    mid: UUID, data: ActionsSave, actor=Depends(require_analytics_admin), db: Session = Depends(get_session)
):
    with db.begin():
        return save_actions(db, mid, actor.id, data)


from typing import Literal  # noqa: E402

from fastapi import Query  # noqa: E402

from aifootball.service.ratings.calculation import calculate_snapshot, publish_snapshot, publish_sources  # noqa: E402
from aifootball.service.ratings.queries import (  # noqa: E402
    get_rankings,
    match_ratings,
    overview,
    performance_publication,
    player_history,
)
from aifootball.service.ratings.schemas import (  # noqa: E402
    AnalyticsOverview,
    MatchRatingsView,
    PerformancePublication,
    PerformancePublicationView,
    RatingCalculate,
    RatingPage,
    RatingPlayerHistory,
    RatingPublish,
    RatingSnapshotResult,
)


@router.get(
    '/tournaments/{tid}/analytics', response_model=AnalyticsOverview, dependencies=[Depends(require_analytics_reader)]
)
def analytics(tid: UUID, db: Session = Depends(get_session)):
    return overview(db, tid)


@router.post('/tournaments/{tid}/analytics/calculate', response_model=RatingSnapshotResult)
def calculate(
    tid: UUID, data: RatingCalculate, actor=Depends(require_analytics_admin), db: Session = Depends(get_session)
):
    payload = data.model_dump(mode='json', exclude={'request_id'})
    with db.begin():
        return calculate_snapshot(db, tid, actor.id, data.request_id, **payload)


@router.post('/tournaments/{tid}/analytics/publish', response_model=RatingSnapshotResult)
def publish(tid: UUID, data: RatingPublish, actor=Depends(require_analytics_admin), db: Session = Depends(get_session)):
    with db.begin():
        return publish_snapshot(db, tid, actor.id, data)


@router.get(
    '/matches/{mid}/performance-publication',
    response_model=PerformancePublicationView,
    dependencies=[Depends(require_analytics_reader)],
)
def read_performance_publication(mid: UUID, db: Session = Depends(get_session)):
    return performance_publication(db, mid)


@router.put('/matches/{mid}/performance-publication', response_model=PerformancePublicationView)
def publish_performance(
    mid: UUID, data: PerformancePublication, actor=Depends(require_analytics_admin), db: Session = Depends(get_session)
):
    with db.begin():
        return publish_sources(db, mid, actor.id, data)


@router.get('/tournaments/{tid}/ratings', response_model=RatingPage, dependencies=[Depends(require_analytics_reader)])
def ratings(
    tid: UUID,
    snapshot_id: UUID | None = None,
    position: str | None = None,
    team_id: UUID | None = None,
    stage_label: str | None = None,
    qualification: Literal['qualified', 'preliminary', 'unknown'] | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_session),
):
    return get_rankings(
        db,
        tid,
        snapshot_id,
        {'position': position, 'team_id': team_id, 'stage_label': stage_label, 'qualification': qualification},
        {'limit': limit, 'offset': offset},
    )


@router.get('/public/tournaments/{tid}/ratings', response_model=RatingPage)
def public_ratings(
    tid: UUID,
    snapshot_id: UUID | None = None,
    position: str | None = None,
    team_id: UUID | None = None,
    stage_label: str | None = None,
    qualification: Literal['qualified', 'preliminary', 'unknown'] | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_session),
):
    return get_rankings(
        db,
        tid,
        snapshot_id,
        {'position': position, 'team_id': team_id, 'stage_label': stage_label, 'qualification': qualification},
        {'limit': limit, 'offset': offset},
        scope='public',
    )


@router.get(
    '/players/{pid}/ratings', response_model=RatingPlayerHistory, dependencies=[Depends(require_analytics_reader)]
)
def history(pid: UUID, tournament_id: UUID, snapshot_id: UUID | None = None, db: Session = Depends(get_session)):
    return player_history(db, pid, tournament_id, snapshot_id)


@router.get('/public/players/{pid}/ratings', response_model=RatingPlayerHistory)
def public_history(pid: UUID, tournament_id: UUID, snapshot_id: UUID | None = None, db: Session = Depends(get_session)):
    return player_history(db, pid, tournament_id, snapshot_id, scope='public')


@router.get('/matches/{mid}/ratings', response_model=MatchRatingsView, dependencies=[Depends(require_analytics_reader)])
def match_rating(mid: UUID, snapshot_id: UUID | None = None, db: Session = Depends(get_session)):
    return match_ratings(db, mid, snapshot_id)


@router.get('/public/matches/{mid}/ratings', response_model=MatchRatingsView)
def public_match_rating(mid: UUID, snapshot_id: UUID | None = None, db: Session = Depends(get_session)):
    return match_ratings(db, mid, snapshot_id, scope='public')


@router.get(
    '/matches/{mid}/action-stats', response_model=TeamActionStats, dependencies=[Depends(require_analytics_reader)]
)
def match_action_stats(
    mid: UUID, period: str = Query('all', pattern=r'^(all|[1-9][0-9]?)$'), db: Session = Depends(get_session)
):
    get_entity(db, Match, mid)
    return private_action_stats(db, mid, period)


@router.get('/public/matches/{mid}/action-stats', response_model=TeamActionStats)
def public_match_action_stats(
    mid: UUID, period: str = Query('all', pattern=r'^(all|[1-9][0-9]?)$'), db: Session = Depends(get_session)
):
    return public_action_stats(db, mid, period)
