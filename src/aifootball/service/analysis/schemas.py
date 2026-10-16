from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal


class JobCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID


class JobView(BaseModel):
    id: UUID
    match_id: UUID
    created_at: datetime
    context_hash: str
    context: dict


class Mutation(JobCreate):
    expected_revision: int = Field(ge=0)


class PointerMutation(Mutation):
    expected_analysis_revision: int = Field(ge=0)


class AssignmentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    track_id: int = Field(ge=0)
    player_id: UUID | None = None
    excluded_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator('excluded_reason')
    @classmethod
    def nonblank_reason(cls, value):
        if value is not None and not value.strip(): raise ValueError('Укажите причину исключения')
        return value.strip() if value else value


class AssignmentsUpdate(Mutation):
    side_map: dict[str, Literal['home', 'away']]
    assignments: list[AssignmentInput] = Field(max_length=50000)

from typing import Any

class RosterPerson(BaseModel):
    player_id: UUID
    side: Literal['home', 'away']
    display_name: str
    shirt_number: str | None

class TeamSnapshot(BaseModel):
    id: UUID
    name: str

class AnalysisContext(BaseModel):
    match_id: UUID
    hall_id: UUID
    teams: dict[str, TeamSnapshot]
    rosters: list[RosterPerson]
    pitch: dict[str, float]
    camera: dict[str, Any]
    units: dict[str, str]

class RunSummary(BaseModel):
    has_understanding: bool = False
    has_events: bool = False
    id: UUID
    job_id: UUID
    created_at: datetime
    status: Literal['review', 'confirmed']
    revision: int
    source_run_id: UUID | None
    partial: bool
    passed: bool

class TrackView(BaseModel):
    track_id: int
    team: Literal['A', 'B'] | None
    role: str
    intervals: list[list[float]]
    thumb: str | None
    has_metrics: bool

class MetricValues(BaseModel):
    distance_m: float | None = None
    observed_s: float | None = None
    m_per_min: float | None = None
    hsr_m: float | None = None
    sprints: int | None = None
    vmax_ms: float | None = None
    heatmap_s: list[list[float]] | None = None
    metric_notes: dict[str, str] = Field(default_factory=dict)
    missing_track_ids: list[int] = Field(default_factory=list)

class PlayerMetric(BaseModel):
    player_id: UUID
    display_name: str
    shirt_number: str | None
    side: Literal['home', 'away']
    track_ids: list[int]
    metrics: MetricValues

class RunView(RunSummary):
    match_id: UUID
    analysis_revision: int
    active_run_id: UUID | None
    published_run_id: UUID | None
    context: AnalysisContext
    manifest: dict[str, Any]
    report: dict[str, Any]
    checks: dict[str, Any]
    tracks: list[TrackView]
    side_map: dict[str, Literal['home', 'away']]
    assignments: list[AssignmentInput]
    players: list[PlayerMetric]

class Overview(BaseModel):
    match_id: UUID
    analysis_revision: int
    active_run_id: UUID | None
    published_run_id: UUID | None
    jobs: list[JobView]
    runs: list[RunSummary]

class HistoryMatch(PlayerMetric):
    match_id: UUID
    run_id: UUID
    scheduled_at: datetime
    teams: dict[str, TeamSnapshot]
    pitch: dict[str, Any]
    partial: bool

class PlayerHistoryView(BaseModel):
    player_id: UUID
    match_count: int
    totals: MetricValues
    matches: list[HistoryMatch]

class PublicMetrics(BaseModel):
    distance_m: float | None
    observed_s: float | None
    m_per_min: float | None
    hsr_m: float | None
    sprints: int | None
    vmax_ms: float | None
    heatmap_s: list[list[float]] | None

class PublicPlayer(BaseModel):
    player_id: UUID
    display_name: str
    shirt_number: str | None
    side: Literal['home', 'away']
    metrics: PublicMetrics

class PublicAnalysis(BaseModel):
    match_id: UUID
    run_id: UUID
    pitch: dict[str, Any]
    teams: dict[str, TeamSnapshot]
    side_map: dict[str, Literal['home', 'away']]
    primary_period_key: str
    video_s: float
    processed_s: float
    partial: bool
    periods: list[dict[str, Any]]
    players: list[PublicPlayer]


class UnderstandingReviewUpdate(Mutation):
    event_id: str = Field(min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    decision: Literal['accepted','corrected','rejected']
    correction: dict[str, Any] | None = None
    reason: str = Field(default='',max_length=500)


class UnderstandingView(BaseModel):
    run_id: UUID
    match_id: UUID
    source_run_id: UUID | None
    status: Literal['review','confirmed']
    revision: int
    understanding: dict[str, Any] | None
    reviews: dict[str, Any]
    side_map_verified: bool
    identity_suggestions: list[dict[str, Any]]
    effective_events: list[dict[str, Any]]
    verified_summary: list[dict[str, Any]]
    history: list[dict[str, Any]]
