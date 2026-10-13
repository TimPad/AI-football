from typing import Annotated,Literal,Union
from uuid import UUID
from pydantic import Field,create_model
from aifootball.service.tournaments.schemas import Input
from aifootball.service.matches.schemas import MatchUpdate,LineupUpdate,StatusUpdate
from aifootball.service.protocol import payloads


class Envelope(Input):
    request_id:UUID
    expected_revision:int=Field(ge=0,strict=True)


PAYLOAD_TYPES={
    'update_match':MatchUpdate,'set_lineup':LineupUpdate,'set_status':StatusUpdate,
    'add_event':payloads.EventChange,'replace_event':payloads.EventChange,'remove_event':payloads.EventRemove,
    'set_totals':payloads.SetTotals,'set_completeness':payloads.CompletenessPatch,'set_notes':payloads.Notes,
    'confirm':payloads.Confirm,'reopen':payloads.Empty,'publish':payloads.Publish,'unpublish':payloads.Empty,
    'remove_attachment':payloads.AttachmentPayload,
    'clock_start':payloads.Empty,'clock_pause':payloads.Empty,'clock_resume':payloads.Empty,
    'clock_set':payloads.ClockSet,'clock_end_period':payloads.Empty,
}
_types=[]
for kind,payload_type in PAYLOAD_TYPES.items():
    name=''.join(part.title() for part in kind.split('_'))+'Command'
    _types.append(create_model(name,__base__=Envelope,kind=(Literal[kind],Field()),payload=(payload_type,Field())))
CommandRequest=Annotated[Union[tuple(_types)],Field(discriminator='kind')]
