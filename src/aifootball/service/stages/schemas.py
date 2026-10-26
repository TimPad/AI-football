"""Настройки этапов, шаблоны форматов, тела запросов и представления таблиц."""
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator, model_validator
from aifootball.service.tournaments.schemas import Input
from aifootball.service.matches.schemas import BroadcastFields, MatchCreate

Criterion = Literal['points', 'h2h_points', 'h2h_goal_diff', 'h2h_goals', 'goal_diff', 'goals_for', 'wins', 'buchholz', 'lot']
Kind = Literal['round_robin', 'groups', 'single_elim', 'double_elim', 'swiss']
Template = Literal['league', 'groups_playoff', 'playoff', 'double_elim', 'swiss']
DrawMethod = Literal['pots', 'snake', 'seeded', 'random', 'scheme', 'manual']
ELIMINATION = ('single_elim', 'double_elim')


class Best(Input):
    place: Annotated[int, Field(ge=1, le=20)]
    count: Annotated[int, Field(ge=1, le=32)]


class Advance(Input):
    per_group: Annotated[int, Field(ge=0, le=32)] = 0
    best: list[Best] = Field(default_factory=list, max_length=3)


class StageConfig(Input):
    kind: Kind
    legs: Literal[1, 2] = 1
    criteria: list[Criterion] | None = None
    # {'entries': 'all'} — все заявки турнира; {'previous': True} — участники из предыдущего этапа.
    source: dict = Field(default_factory=lambda: {'entries': 'all'})
    group_count: Annotated[int, Field(ge=2, le=16)] | None = None
    advance: Advance = Field(default_factory=Advance)
    playoff_teams: Annotated[int, Field(ge=2, le=64)] | None = None
    third_place: bool = False
    two_leg_rounds: list[Annotated[int, Field(ge=1, le=8)]] = Field(default_factory=list, max_length=8)
    grand_final_reset: bool = False
    rounds: Annotated[int, Field(ge=1, le=15)] | None = None

    @field_validator('source')
    @classmethod
    def known_source(cls, value):
        if value not in ({'entries': 'all'}, {'previous': True}): raise ValueError('Неизвестный источник участников')
        return value

    @model_validator(mode='after')
    def coherent(self):
        if self.kind == 'groups' and self.group_count is None: raise ValueError('Укажите число групп')
        if self.criteria is not None:
            if not self.criteria or self.criteria[0] != 'points': raise ValueError('Первым критерием должны быть очки')
            if len(set(self.criteria)) != len(self.criteria): raise ValueError('Критерии повторяются')
            if 'buchholz' in self.criteria and self.kind != 'swiss':
                raise ValueError('Бухгольц — только для швейцарской системы')
        return self

    def effective_criteria(self):
        from aifootball.service.stages.rules.standings import DEFAULT_CRITERIA, SWISS_CRITERIA
        return tuple(self.criteria or (SWISS_CRITERIA if self.kind == 'swiss' else DEFAULT_CRITERIA))


class StageInput(Input):
    request_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=100)
    regulation_id: UUID
    config: StageConfig


class StagePatch(Input):
    expected_revision: int = Field(ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    regulation_id: UUID | None = None
    config: StageConfig | None = None


class FormatCreate(Input):
    request_id: UUID = Field(default_factory=uuid4)
    template: Template
    regulation_id: UUID
    playoff_regulation_id: UUID | None = None
    group_count: Annotated[int, Field(ge=2, le=16)] = 2
    per_group: Annotated[int, Field(ge=1, le=16)] = 2
    best_thirds: Annotated[int, Field(ge=0, le=16)] = 0
    legs: Literal[1, 2] = 1
    playoff_teams: Annotated[int, Field(ge=2, le=64)] | None = None
    third_place: bool = False
    grand_final_reset: bool = False
    rounds: Annotated[int, Field(ge=1, le=15)] | None = None


def template_stages(template, params):
    """Этапы шаблона: [{'name', 'kind', 'config', 'playoff'}]; playoff — брать регламент плей-офф."""
    get = params.get
    playoff = {'name': 'Плей-офф', 'kind': 'single_elim', 'playoff': True,
               'config': {'kind': 'single_elim', 'third_place': bool(get('third_place')), 'source': {'previous': True}}}
    if template == 'league':
        stages = [{'name': 'Лига', 'kind': 'round_robin', 'config': {'kind': 'round_robin', 'legs': get('legs', 1)}}]
    elif template == 'groups_playoff':
        best = [{'place': get('per_group', 2) + 1, 'count': get('best_thirds')}] if get('best_thirds') else []
        stages = [{'name': 'Групповой этап', 'kind': 'groups', 'config': {
            'kind': 'groups', 'legs': get('legs', 1), 'group_count': get('group_count', 2),
            'advance': {'per_group': get('per_group', 2), 'best': best}}}, playoff]
    elif template == 'playoff':
        stages = [{**playoff, 'config': {**playoff['config'], 'source': {'entries': 'all'}}}]
    elif template == 'double_elim':
        stages = [{'name': 'Двойное выбывание', 'kind': 'double_elim', 'playoff': True,
                   'config': {'kind': 'double_elim', 'grand_final_reset': bool(get('grand_final_reset'))}}]
    else:
        stages = [{'name': 'Швейцарская система', 'kind': 'swiss', 'config': {'kind': 'swiss', 'rounds': get('rounds')}}]
    if template in ('league', 'swiss') and get('playoff_teams'):
        stages[0]['config']['playoff_teams'] = get('playoff_teams')
        stages.append(playoff)
    for stage in stages: StageConfig.model_validate(stage['config'])
    return stages


class DrawInput(Input):
    method: DrawMethod
    seed: Annotated[int, Field(ge=0, le=2**31 - 1)] = 0
    seeding: list[UUID] = Field(default_factory=list, max_length=128)
    # Ручная правка: составы групп (списки заявок) или порядок источников сетки/туров.
    placement: list[Any] | None = Field(default=None, max_length=128)


class DrawConfirm(DrawInput):
    request_id: UUID = Field(default_factory=uuid4)
    expected_revision: int = Field(ge=0)


class LotInput(Input):
    request_id: UUID = Field(default_factory=uuid4)
    group: str = Field(min_length=1, max_length=20)
    order: list[UUID] = Field(min_length=2, max_length=64)


class NextRound(Input):
    request_id: UUID = Field(default_factory=uuid4)
    expected_revision: int = Field(ge=0)


class FixtureSchedule(BroadcastFields):
    request_id: UUID = Field(default_factory=uuid4)
    scheduled_at: datetime
    hall_id: UUID
    camera_profile_id: UUID | None = None
    venue_label: str = Field(default='', max_length=200)
    referees: list[str] = Field(default_factory=list, max_length=10)
    _aware = field_validator('scheduled_at')(MatchCreate.aware.__func__)


class FixtureReplace(Input):
    request_id: UUID = Field(default_factory=uuid4)
    side: Literal['home', 'away']
    entry_id: UUID


# Представления.

class TeamRef(BaseModel):
    entry_id: UUID
    team_id: UUID
    name: str
    logo_id: UUID | None = None


class Side(BaseModel):
    team: TeamRef | None = None
    label: str


class LegView(BaseModel):
    match_id: UUID | None = None
    fixture_id: UUID | None = None
    leg: int
    scheduled_at: datetime | None = None
    status: str | None = None
    score: dict[str, int | None] | None = None
    shootout: dict[str, int | None] | None = None


class PairView(BaseModel):
    key: str
    round_no: int
    slot: int
    bracket: str | None = None
    group_no: int | None = None
    label: str
    home: Side
    away: Side
    bye: bool = False
    legs: list[LegView]
    winner: Literal['home', 'away'] | None = None
    note: str | None = None
    can_schedule: bool = False
    changed: bool = False


class RowView(BaseModel):
    place: int
    team: TeamRef
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_diff: int
    points: int
    zone: Literal['advance', 'best'] | None = None
    tied: bool = False


class GroupView(BaseModel):
    group_no: int
    name: str
    rows: list[RowView]
    needs_lot: bool = False


class RoundView(BaseModel):
    round_no: int
    name: str
    pairs: list[PairView]


class SectionView(BaseModel):
    key: Literal['upper', 'lower', 'final', 'rounds']
    name: str
    rounds: list[RoundView]


class DrawView(BaseModel):
    id: UUID
    version: int
    method: str
    seed: int
    seeding: list[Any]
    placement: list[Any]
    confirmed_at: datetime


class StageView(BaseModel):
    id: UUID | None = None
    position: int
    name: str
    kind: Kind
    status: Literal['draft', 'drawn', 'started', 'completed']
    criteria: list[str]
    config: dict | None = None
    regulation_id: UUID | None = None
    revision: int = 0
    draw: DrawView | None = None
    groups: list[GroupView] = Field(default_factory=list)
    sections: list[SectionView] = Field(default_factory=list)
    can_next_round: bool = False


class StandingsView(BaseModel):
    implicit: bool = False
    stages: list[StageView]


class DrawPreview(BaseModel):
    method: str
    seed: int
    seeding: list[Any]
    placement: list[Any]
    groups: list[list[TeamRef | Side]] = Field(default_factory=list)
    pairs: list[PairView] = Field(default_factory=list)
    pots: dict[str, int] = Field(default_factory=dict)
    kept: int = 0
    cancelled: int = 0
    error: str | None = None


class FixtureView(BaseModel):
    id: UUID
    stage_id: UUID
    stage_name: str
    key: str
    leg: int
    round_no: int
    group_no: int | None = None
    bracket: str | None = None
    label: str
    home: Side
    away: Side
    match_id: UUID | None = None
    can_schedule: bool = False
