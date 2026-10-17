from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict

class TeamTaskCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID
    team_id:UUID
    expected_run_revision:int=Field(ge=0)

class TeamDecision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    group_id:str
    player_id:UUID|None=None
    kind:Literal['player','unknown','material_issue']='player'
    reason:str=Field(default='',max_length=500)

class TeamTaskCommand(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID
    expected_revision:int=Field(ge=0)

class TeamTaskDraft(TeamTaskCommand):
    decisions:list[TeamDecision]=Field(max_length=50000)

class TeamTaskReason(TeamTaskCommand):
    reason:str=Field(min_length=1,max_length=1000)

class TeamTrack(BaseModel):
    track_id:int
    intervals:list[list[float]]
    has_thumbnail:bool

class TeamGroup(BaseModel):
    id:str
    tracks:list[TeamTrack]

class TeamPlayer(BaseModel):
    player_id:UUID
    display_name:str
    shirt_number:str|None=None

class TeamTaskView(BaseModel):
    id:UUID
    run_id:UUID
    match_id:UUID
    team_id:UUID
    team_name:str
    opponent_name:str
    scheduled_at:datetime
    side:Literal['home','away']
    status:str
    revision:int
    expires_at:datetime
    reason:str
    groups:list[TeamGroup]
    players:list[TeamPlayer]
    draft:list[TeamDecision]
    confirmed_by_kind:str|None=None
    confirmation_id:UUID|None=None

class TeamTaskList(BaseModel):
    items:list[TeamTaskView]
    total:int
