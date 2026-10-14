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
