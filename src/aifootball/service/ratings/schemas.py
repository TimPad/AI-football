from datetime import datetime
from typing import Annotated,Literal,Any
from uuid import UUID
from pydantic import BaseModel,Field,StrictBool
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
