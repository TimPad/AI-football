from typing import Literal
from uuid import UUID
from pydantic import Field
from aifootball.service.tournaments.schemas import Input
from aifootball.service.protocol.events import Event
from typing import Annotated

Count=Annotated[int,Field(ge=0,le=100000,strict=True)]

class TeamTotals(Input):
    score:Count|None=None
    fouls:Count|None=None
    yellow_cards:Count|None=None
    dismissals:Count|None=None
    period_scores:dict[int,Count|None]=Field(default_factory=dict)

class ReportedTotals(Input):
    home:TeamTotals=Field(default_factory=TeamTotals)
    away:TeamTotals=Field(default_factory=TeamTotals)

class ShootoutTotals(Input):
    home:Count|None=None
    away:Count|None=None

CompletenessValue=Literal["unknown","partial","complete"]
class Completeness(Input):
    goals:CompletenessValue="unknown"
    assists:CompletenessValue="unknown"
    fouls:CompletenessValue="unknown"
    cards:CompletenessValue="unknown"
    lineup:CompletenessValue="unknown"
    time:CompletenessValue="unknown"


class ClockState(Input):
    period:int=Field(default=1,ge=1)
    phase:Literal['not_started','running','paused','ended']='not_started'
    elapsed_ms:int=Field(default=0,ge=0)
    anchor_utc_ms:int|None=None
    break_started_utc_ms:int|None=None
    source:Literal['manual']='manual'
    warning:str|None=None


class ProtocolDocument(Input):
    events:list[Event]=Field(default_factory=list,max_length=10000)
    reported_totals:ReportedTotals=Field(default_factory=ReportedTotals)
    shootout_totals:ShootoutTotals=Field(default_factory=ShootoutTotals)
    completeness:Completeness=Field(default_factory=Completeness)
    result_type:Literal['played','technical']='played'
    technical_reason:str|None=None
    notes:str=Field(default='',max_length=20000)
    public_notes:str=Field(default='',max_length=20000)
    attachment_ids:list[UUID]=Field(default_factory=list)
    draft:bool=True


class Command(Input):
    request_id:UUID
    expected_revision:int=Field(ge=0)
    kind:str=Field(min_length=1,max_length=50)
    payload:dict=Field(default_factory=dict)
