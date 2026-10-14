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
class HallView(NamedView):
    revision: int
    address: str
    pitch_length_m: float
    pitch_width_m: float
    ceiling_height_m: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    surface: str
    description: str
class CameraProfileView(EntityView):
    hall_id: UUID
    name: str
    version: int
    hall_revision: int
    pitch_length_m: float
    pitch_width_m: float
    frame_width: int
    frame_height: int
    points: list[dict]
    pitch_polygon_px: list[list[float]]
    homography: list[list[float]]
    calibration: dict | None = None
    reprojection_error_m: float
    leave_one_out_error_m: float | None = None
    matches_current_dimensions: bool
class PublicHall(BaseModel):
    id: UUID
    name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    pitch_length_m: float
    pitch_width_m: float
class TeamView(NamedView):
    revision: int = 0
    description: str = ''
    logo_id: UUID | None = None
class PlayerView(NamedView):
    revision: int = 0
    photo_id: UUID | None = None
    birth_date: date | None = None
    position: Literal['goalkeeper','defender','winger','forward','universal'] | None = None
    height_cm: int | None = None
    weight_kg: float | None = None
class TeamMemberView(EntityView):
    team_id: UUID
    player_id: UUID
    shirt_number: str | None
    active: bool
    player: PlayerView
class TeamProfile(TeamView):
    players: list[TeamMemberView]
class CatalogImageView(EntityView):
    size: int
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
    team: TeamView
class RosterPlayer(EntityView):
    entry_id: UUID
    player_id: UUID
    shirt_number: str | None
    active: bool
    player: PlayerView
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
    hall_id: UUID | None = None
    hall_snapshot: HallView | None = None
    camera_profile_id: UUID | None = None
    broadcast_url: str | None = None
    broadcast_embed_url: str | None = None
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
    can_manage_analytics: bool = False
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
    hall: PublicHall | None = None
    regulation: PublicRegulation
    lineup: list[PublicLineup]
    protocol: PublicDocument
    projection: Projection


class PublicTournament(BaseModel):
    id: UUID
    name: str
    season: str
    starts_on: date
    ends_on: date
    timezone: str


class PublicScore(BaseModel):
    home: int | None
    away: int | None


class PublicMatch(BaseModel):
    id: UUID
    tournament: PublicTournament
    home_name: str
    away_name: str
    scheduled_at: datetime
    venue_label: str
    hall: PublicHall | None = None
    status: Literal['scheduled','live','ended','postponed','cancelled']
    schedule_slot_s: int
    broadcast_url: str | None
    broadcast_embed_url: str | None
    public_protocol_id: UUID | None
    score: PublicScore
