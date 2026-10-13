from uuid import UUID
from pydantic import Field
from typing import Literal
from aifootball.service.tournaments.schemas import Input
from aifootball.service.protocol.events import Event
from aifootball.service.protocol.schemas import ReportedTotals,ShootoutTotals,CompletenessValue


class EventChange(Input):
    event:Event
    related_events:list[Event]=Field(default_factory=list,max_length=3)


class EventRemove(Input):
    event_id:UUID
    related_ids:list[UUID]=Field(default_factory=list,max_length=3)


class SetTotals(Input):
    reported_totals:ReportedTotals|None=None
    shootout_totals:ShootoutTotals|None=None
    result_type:Literal['played','technical']|None=None
    technical_reason:str|None=Field(default=None,max_length=2000)


class CompletenessPatch(Input):
    goals:CompletenessValue|None=None
    assists:CompletenessValue|None=None
    fouls:CompletenessValue|None=None
    cards:CompletenessValue|None=None
    lineup:CompletenessValue|None=None
    time:CompletenessValue|None=None


class Notes(Input):
    notes:str|None=Field(default=None,max_length=20000)
    public_notes:str|None=Field(default=None,max_length=20000)


class Confirm(Input):
    acknowledge_incomplete:bool=False


class Publish(Input):
    version_id:UUID


class Empty(Input):
    pass


class AttachmentPayload(Input):
    attachment_id:UUID


class ClockSet(Input):
    elapsed_ms:int=Field(ge=0,le=86400000,strict=True)
    reason:str=Field(min_length=1,max_length=2000)
