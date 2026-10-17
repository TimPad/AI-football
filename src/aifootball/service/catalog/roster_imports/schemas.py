from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field
from aifootball.service.tournaments.schemas import Input


class PlayerDecision(Input):
    player_id: UUID | None = None
    create_new: bool = False


class ImportPreviewInput(Input):
    expected_revision: int = Field(ge=0)
    sheet: str = Field(min_length=1, max_length=100)
    mapping: dict[str, int] = Field(max_length=12)
    edits: dict[str, dict[str, str | None]] = Field(default_factory=dict, max_length=1000)
    decisions: dict[str, PlayerDecision] = Field(default_factory=dict, max_length=1000)
    team_decisions: dict[str, str] = Field(default_factory=dict, max_length=64)
    excluded_rows: list[str] = Field(default_factory=list, max_length=1000)


class ImportCommit(Input):
    request_id: UUID
    expected_revision: int = Field(ge=0)


class ImportSheet(BaseModel):
    name: str
    headers: list[str]
    row_count: int


class ImportCandidate(BaseModel):
    id: UUID
    name: str
    archived: bool = False


class ImportRow(BaseModel):
    id: str
    source_row: int
    team_name: str
    name: str
    shirt_number: str | None = None
    player_id: UUID | None = None
    team_id: UUID | None = None
    player_candidates: list[ImportCandidate] = Field(default_factory=list)
    team_candidates: list[ImportCandidate] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    excluded: bool = False
    action: str
    values: dict[str, str | None] = Field(default_factory=dict)


class ImportResult(BaseModel):
    teams_created: int
    players_created: int
    players_reused: int
    entries_updated: int
    skipped_rows: int
    links: list[dict[str, str]]


class ImportView(BaseModel):
    id: UUID
    revision: int
    scope: Literal['team', 'tournament']
    target_id: UUID
    entry_id: UUID | None = None
    status: str
    expires_at: datetime
    sheets: list[ImportSheet]
    rows: list[ImportRow]
    summary: dict[str, int]
    configuration: dict[str, Any]
    can_commit: bool
    result: ImportResult | None = None
