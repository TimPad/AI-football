from datetime import datetime
from typing import Annotated,Literal,Any
from uuid import UUID
from pydantic import field_validator, BaseModel,Field,StrictBool
from aifootball.service.tournaments.schemas import Input

Millis=Annotated[int,Field(strict=True,ge=0,le=86400000)]
Interval=Annotated[list[Millis],Field(min_length=2,max_length=2)]
Role=Literal['goalkeeper','fixo','ala','pivot','universal','unknown']


class RoleIntervals(Input):
    role:Role
    intervals:list[Interval]=Field(default_factory=list,max_length=1000)


class PlayerParticipation(Input):
    player_id:UUID
    presence:list[Interval]|None=Field(default=None,max_length=1000)
    completeness:Literal['complete','partial','unknown']='unknown'
    appeared:StrictBool|None=None
    roles:list[RoleIntervals]=Field(default_factory=list,max_length=6)


class InitialFive(Input):
    home:list[UUID]=Field(default_factory=list,max_length=1000)
    away:list[UUID]=Field(default_factory=list,max_length=1000)


class PossessionIntervals(Input):
    home:list[Interval]|None=Field(default=None,max_length=10000)
    away:list[Interval]|None=Field(default=None,max_length=10000)


class Manpower(Input):
    side:Literal['home','away']
    start_ms:Millis
    end_ms:Millis
    max_players:int=Field(strict=True,ge=1,le=1000)
    powerplay:StrictBool=False
    reason:str=Field(min_length=1,max_length=500)


class ParticipationDocument(Input):
    clock_basis:Literal['game','video']
    time_basis:Literal['reviewed_effective','official_clean','running_clock']
    analysis_scope:Literal['full_match','continuous_excerpt','highlights','unknown']='unknown'
    duration_ms:int=Field(strict=True,gt=0,le=86400000)
    source_analysis_run_id:UUID|None=None
    source_protocol_version_id:UUID|None=None
    initial_five:InitialFive=Field(default_factory=InitialFive)
    players:list[PlayerParticipation]=Field(default_factory=list,max_length=2000)
    play_intervals:list[Interval]|None=Field(default=None,max_length=10000)
    possession_intervals:PossessionIntervals=Field(default_factory=PossessionIntervals)
    manpower:list[Manpower]=Field(default_factory=list,max_length=1000)
    notes:str=Field(default='',max_length=2000)


class ParticipationSave(Input):
    request_id:UUID
    expected_revision:int=Field(strict=True,ge=0)
    expected_match_revision:int=Field(strict=True,ge=0)
    status:Literal['review','confirmed']='review'
    document:ParticipationDocument


class ParticipationSummary(BaseModel):
    id:UUID
    revision:int
    status:Literal['review','confirmed']
    created_at:datetime


class ParticipationView(ParticipationSummary):
    match_id:UUID
    created_by:UUID
    context_hash:str
    document:ParticipationDocument
    provenance:dict[str,Any]
    lineup:list[dict[str,Any]]
    exposures:dict[str,dict[str,dict[str,float|None]]]


class ParticipationOverview(BaseModel):
    match_id:UUID
    match_revision:int
    revision:int
    current:ParticipationView|None
    versions:list[ParticipationSummary]
    lineup:list[dict[str,Any]]
    rules:dict[str,Any]
    protocol_versions:list[dict[str,Any]]
    analysis_runs:list[dict[str,Any]]


ActionKind=Literal['shot','pass','carry','duel','recovery','shot_block','turnover','save','distribution','error','goal_candidate']
ActionCategory=Literal['shots','passes','carries','duels','recoveries','shot_blocks','turnovers','saves','distribution','errors']
Point=Annotated[list[Annotated[float,Field(strict=True,ge=0,le=300,allow_inf_nan=False)]],Field(min_length=2,max_length=2)]


class ActionInput(Input):
    id:UUID
    kind:ActionKind
    player_id:UUID|None=None
    recipient_id:UUID|None=None
    opponent_id:UUID|None=None
    side:Literal['home','away']|None=None
    role:Role|None=None
    start_ms:Millis|None=None
    end_ms:Millis|None=None
    success:StrictBool|None=None
    on_target:StrictBool|None=None
    outcome:Literal['goal','saved','off_target','success','failure','unknown']='unknown'
    possession_id:UUID|None=None
    start_xy:Point|None=None
    end_xy:Point|None=None
    attacking_direction:Literal['left','right','unknown']='unknown'
    penalty_conceded:StrictBool=False
    source_episode_id:str|None=Field(default=None,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    source_video_ms:Millis|None=None
    shot_id:UUID|None=None
    decision:Literal['accepted','rejected']='accepted'
    notes:str=Field(default='',max_length=500)


class ActionLink(Input):
    kind:Literal['canonical','incident']='canonical'
    canonical_event_id:UUID
    source_event_id:UUID


class CategoryCoverage(Input):
    status:Literal['unknown','partial','complete']='unknown'
    intervals:list[Interval]|None=Field(default=None,max_length=10000)
    player_ids:list[UUID]|None=Field(default=None,max_length=2000)


class ActionDocument(Input):
    clock_basis:Literal['game','video']
    analysis_scope:Literal['full_match','continuous_excerpt','highlights','unknown']='unknown'
    duration_ms:int=Field(strict=True,gt=0,le=86400000)
    source_participation_version_id:UUID|None=None
    source_analysis_run_id:UUID|None=None
    source_protocol_version_id:UUID|None=None
    actions:list[ActionInput]=Field(default_factory=list,max_length=10000)
    links:list[ActionLink]=Field(default_factory=list,max_length=20000)
    completeness:dict[ActionCategory,list[CategoryCoverage]]=Field(default_factory=dict)
    notes:str=Field(default='',max_length=2000)


class ActionsSave(Input):
    request_id:UUID
    expected_revision:int=Field(strict=True,ge=0)
    expected_match_revision:int=Field(strict=True,ge=0)
    status:Literal['review','confirmed']='review'
    document:ActionDocument


class ActionsView(ParticipationSummary):
    match_id:UUID
    created_by:UUID
    context_hash:str
    document:ActionDocument
    provenance:dict[str,Any]
    lineup:list[dict[str,Any]]
    canonical_actions:list[dict[str,Any]]


class ActionsOverview(BaseModel):
    match_id:UUID
    match_revision:int
    revision:int
    current:ActionsView|None
    versions:list[ParticipationSummary]
    lineup:list[dict[str,Any]]
    rules:dict[str,Any]
    pitch:dict[str,Any]|None
    protocol_versions:list[dict[str,Any]]
    analysis_runs:list[dict[str,Any]]
    participation_versions:list[ParticipationSummary]


class RatingCalculate(Input):
    request_id:UUID
    expected_revision:int=Field(strict=True,ge=0)
    scope:Literal['private','public']='private'
    profile_id:Literal['per10','per10-possession']='per10'
    time_basis:Literal['reviewed_effective','official_clean','running_clock']='reviewed_effective'
    level:str=Field(default='amateur',min_length=1,max_length=100)
    cutoff:datetime|None=None

    @field_validator('cutoff')
    @classmethod
    def aware_cutoff(cls,value):
        if value is not None and value.tzinfo is None:raise ValueError('Укажите часовой пояс cutoff')
        return value


class RatingPublish(Input):
    request_id:UUID
    expected_revision:int=Field(strict=True,ge=0)
    snapshot_id:UUID


class PerformancePublication(Input):
    request_id:UUID
    expected_revision:int=Field(strict=True,ge=0)
    expected_match_revision:int=Field(strict=True,ge=0)
    participation_version_id:UUID|None=None
    action_version_id:UUID|None=None
    approve_policy:StrictBool=False


class MetricFactView(BaseModel):
    value:float|None
    numerator:float|None
    denominator:float|None
    unit:str
    completeness:str
    reason:str|None


class RatingMatchView(BaseModel):
    match_id:UUID
    player_id:UUID
    display_name:str
    role:str
    team_id:UUID
    team_name:str
    stage_label:str|None=None
    scheduled_at:str
    appeared:bool|None
    eligible_play_minutes:float|None
    played_minutes:float|None
    coverage:float|None
    score:float|None
    display_rating:float|None
    components:dict[str,float|None]
    contributions:dict[str,float|None]
    feature_scores:dict[str,float|None]
    facts:dict[str,MetricFactView]
    reasons:list[str]
    model_version:str
    reference_version:str
    profile_id:str
    time_basis:str
    moments:list[dict[str,Any]]=Field(default_factory=list)
    physical:dict[str,Any]=Field(default_factory=dict)
    explanation:dict[str,Any]=Field(default_factory=dict)


class RatingSummaryView(BaseModel):
    player_id:UUID
    display_name:str
    role:str|None
    rank:int|None
    qualification:Literal['qualified','preliminary','unknown']
    score:float|None
    display_rating:float|None
    match_count:int
    rated_match_count:int
    eligible_play_minutes:float
    played_minutes:float|None
    known_played_minutes:float
    rated_minutes:float
    weight_sum:float
    coverage:float|None
    baseline_influence:float|None
    facts:dict[str,MetricFactView]=Field(default_factory=dict)
    teams:list[dict[str,str]]=Field(default_factory=list)
    reasons:list[str]=Field(default_factory=list)


class RatingPage(BaseModel):
    snapshot_id:UUID|None
    calculated_at:datetime|None=None
    published_at:datetime|None=None
    scope:Literal['private','public']
    edition:dict[str,str]=Field(default_factory=dict)
    label:str='Пилотная методика'
    items:list[RatingSummaryView]
    total:int
    limit:int
    offset:int
    reason:str|None=None
    filters:dict[str,Any]=Field(default_factory=dict)


class RatingPlayerHistory(BaseModel):
    snapshot_id:UUID|None
    summary:list[RatingSummaryView]
    matches:list[RatingMatchView]


class RatingSnapshotResult(BaseModel):
    stale:bool=False
    snapshot_id:UUID
    revision:int
    scope:Literal['private','public']
    calculated_at:datetime
    published_at:datetime|None
    source_fingerprint:str
    summary:dict[str,Any]
    settings:dict[str,Any]


class AnalyticsOverview(BaseModel):
    revision:int
    policy:dict[str,Any]
    private_snapshot_id:UUID|None
    public_snapshot_id:UUID|None
    policy_approved:bool
    snapshots:list[RatingSnapshotResult]
    sources:list[dict[str,Any]]


class PerformancePublicationView(BaseModel):
    revision:int
    match_id:UUID
    participation_version_id:UUID|None
    action_version_id:UUID|None
    policy_approved:bool


class MatchRatingsView(BaseModel):
    overall:list[RatingMatchView]=Field(default_factory=list)
    snapshot_id:UUID|None
    items:list[RatingMatchView]


class StatValue(BaseModel):
    value:float|None
    numerator:int|None=None
    denominator:int|None=None
    unknown:int=0


class TeamStatRow(BaseModel):
    key:str
    label:str
    group:Literal['shots','passes','defense','goalkeeping']
    category:str
    unit:Literal['count','percent']
    coverage:Literal['complete','partial','unknown']
    source:Literal['manual','cv_auto']='manual'
    home:StatValue
    away:StatValue


class ShotPoint(BaseModel):
    id:str
    side:Literal['home','away']
    player_id:UUID|None
    x:float
    y:float
    goal:bool
    on_target:bool
    blocked:bool
    outcome:str
    period:str|None
    start_ms:int|None


class StatsSource(BaseModel):
    kind:Literal['manual','cv_auto','mixed']
    action_version_id:UUID|None
    run_id:UUID|None
    run_published:bool
    revision:int
    status:Literal['review','confirmed']
    published:bool
    clock_basis:Literal['game','video']|None
    analysis_scope:str


class StatsPeriod(BaseModel):
    key:str
    label:str


class PitchSize(BaseModel):
    length_m:float
    width_m:float


class TeamActionStats(BaseModel):
    source:StatsSource
    periods:list[StatsPeriod]
    period:str
    untimed:int
    coverage:dict[str,Literal['complete','partial','unknown']]
    rows:list[TeamStatRow]
    shots:list[ShotPoint]
    pitch:PitchSize|None
