"""Public HTTP response contracts; OpenAPI is the frontend's source of types."""
from datetime import date, datetime
from uuid import UUID
from typing import Generic, TypeVar, Literal
from pydantic import BaseModel
from aifootball.service.tournaments.schemas import Regulation
from aifootball.service.protocol.schemas import ProtocolDocument, ClockState, ReportedTotals, ShootoutTotals, Completeness
from aifootball.service.protocol.projection import Projection

T = TypeVar('T')
class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
class EntityView(BaseModel):
    id: UUID
    created_at: datetime
class NamedView(EntityView):
    name: str
    archived: bool
class TournamentView(NamedView):
    season: str
    starts_on: date
    ends_on: date
    timezone: str
    revision: int
class RegulationView(EntityView):
    tournament_id: UUID
    variant_name: str
    version: int
    rules: Regulation
    total_s: int | None = None
class Preset(BaseModel):
    name: str
    rules: Regulation
class EntryView(EntityView):
    tournament_id: UUID
    team_id: UUID
    revision: int
    team: NamedView
class RosterPlayer(EntityView):
    entry_id: UUID
    player_id: UUID
    shirt_number: str | None
    active: bool
    player: NamedView
class RosterView(EntryView):
    players: list[RosterPlayer]
class LineupView(EntityView):
    match_id: UUID
    entry_player_id: UUID
    player_id: UUID
    side: Literal['home','away']
    shirt_number: str | None
    display_name: str
class MatchView(EntityView):
    match_id: UUID
    tournament_id: UUID
    home_entry_id: UUID
    away_entry_id: UUID
    regulation_id: UUID
    regulation_override: Regulation | None
    override_reason: str | None
    scheduled_at: datetime
    venue_label: str
    referees: list[str]
    status: Literal['scheduled','live','ended','postponed','cancelled']
    revision: int
    protocol: ProtocolDocument
    clock: ClockState
    published_version_id: UUID | None
    lineup: list[LineupView]
    projection: Projection
    regulation: RegulationView
    home: EntryView
    away: EntryView
    server_now_ms: int
class SessionView(BaseModel):
    id: UUID
    login: str
    csrf_token: str
class VersionView(EntityView):
    match_id: UUID
    number: int
    snapshot: MatchView
    confirmed_by: UUID
    confirmed_at: datetime
    published_at: datetime | None
    public_id: UUID | None

# Build a separate, narrow public event schema. Serialization never supplies
# private note/time fields omitted by the public snapshot endpoint.
from typing import Annotated, Union, get_args
from pydantic import Field, create_model, ConfigDict
from aifootball.service.protocol.events import Event
_public_events=[]
for event_type in get_args(get_args(Event)[0]):
    fields={name:(field.annotation,Field()) for name,field in event_type.model_fields.items()
            if name not in {'notes','video_ms','created_at'}}
    _public_events.append(create_model('Public'+event_type.__name__,__config__=ConfigDict(extra='forbid'),**fields))
PublicEvent=Annotated[Union[tuple(_public_events)],Field(discriminator='kind')]
class PublicLineup(BaseModel):
    player_id: UUID
    display_name: str
    shirt_number: str | None
    side: Literal['home','away']
class PublicDocument(BaseModel):
    events: list[PublicEvent]
    reported_totals: ReportedTotals
    shootout_totals: ShootoutTotals
    completeness: Completeness
    result_type: Literal['played','technical']
    technical_reason: str | None
    public_notes: str
    draft: bool
class PublicRegulation(BaseModel):
    rules: Regulation
    total_s: int
class PublicProtocol(BaseModel):
    number: int
    confirmed_at: datetime
    published_at: datetime
    home_name: str
    away_name: str
    scheduled_at: datetime
    venue_label: str
    regulation: PublicRegulation
    lineup: list[PublicLineup]
    protocol: PublicDocument
    projection: Projection
