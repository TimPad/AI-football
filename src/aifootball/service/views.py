"""Public HTTP response contracts; OpenAPI is the frontend's source of types."""
from datetime import date, datetime
from uuid import UUID
from typing import Generic, TypeVar, Literal
from pydantic import BaseModel
from aifootball.service.tournaments.schemas import Regulation
from aifootball.service.protocol.schemas import ProtocolDocument, ClockState
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
