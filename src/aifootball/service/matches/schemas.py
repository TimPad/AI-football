from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import Field,field_validator
from aifootball.service.tournaments.schemas import Input,Regulation

MatchStatus=Literal['scheduled','live','ended','postponed','cancelled']


class MatchCreate(Input):
    home_entry_id:UUID
    away_entry_id:UUID
    regulation_id:UUID
    scheduled_at:datetime
    venue_label:str=Field(default='',max_length=200)
    referees:list[str]=Field(default_factory=list,max_length=10)
    regulation_override:Regulation|None=None
    override_reason:str|None=Field(default=None,max_length=2000)

    @field_validator('scheduled_at')
    @classmethod
    def aware(cls,value):
        if value is None or value.tzinfo is None: raise ValueError('Дата матча должна содержать часовой пояс')
        return value


class MatchUpdate(Input):
    scheduled_at:datetime|None=None
    venue_label:str|None=Field(default=None,max_length=200)
    referees:list[str]|None=Field(default=None,max_length=10)
    regulation_override:Regulation|None=None
    override_reason:str|None=Field(default=None,max_length=2000)
    _aware=field_validator('scheduled_at')(MatchCreate.aware.__func__)


class LineupSelection(Input):
    entry_player_id:UUID
    side:Literal['home','away']


class LineupUpdate(Input):
    players:list[LineupSelection]=Field(max_length=2000)


class StatusUpdate(Input):
    status:MatchStatus


class ApplyMatch(Input):
    id:UUID
    expected_revision:int=Field(ge=0)


class PreviewRules(Input):
    match_ids:list[UUID]=Field(min_length=1,max_length=100)


class ApplyRules(Input):
    request_id:UUID
    matches:list[ApplyMatch]=Field(min_length=1,max_length=100)
