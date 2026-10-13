from typing import Literal
from uuid import UUID
from pydantic import Field
from aifootball.service.tournaments.schemas import Input


class ClockState(Input):
    period:int=Field(default=1,ge=1)
    phase:Literal['not_started','running','paused','ended']='not_started'
    elapsed_ms:int=Field(default=0,ge=0)
    anchor_utc_ms:int|None=None
    break_started_utc_ms:int|None=None
    source:Literal['manual']='manual'


class ProtocolDocument(Input):
    events:list[dict]=Field(default_factory=list)
    reported_totals:dict=Field(default_factory=dict)
    shootout_totals:dict=Field(default_factory=dict)
    completeness:dict=Field(default_factory=lambda:{k:'unknown' for k in ['goals','assists','fouls','cards','lineup','time']})
    result_type:Literal['played','technical']='played'
    technical_reason:str|None=None
    notes:str=''
    public_notes:str=''
    attachment_ids:list[UUID]=Field(default_factory=list)
    draft:bool=True


class Command(Input):
    request_id:UUID
    expected_revision:int=Field(ge=0)
    kind:str=Field(min_length=1,max_length=50)
    payload:dict=Field(default_factory=dict)
