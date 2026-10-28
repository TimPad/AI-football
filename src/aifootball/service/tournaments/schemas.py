from datetime import date
from uuid import UUID, uuid4
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, model_validator, computed_field

Positive = Annotated[int, Field(gt=0,le=86400,strict=True)]
Nonnegative = Annotated[int, Field(ge=0,le=86400,strict=True)]
ClockMode = Literal['clean','running','mixed']


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True,json_schema_serialization_defaults_required=True)


class Timeouts(Input):
    allowed: bool=True
    duration_s: Positive=60
    count: Nonnegative=1
    scope: Literal['period','match']='period'


class Extra(Input):
    enabled: bool=False
    periods_s: list[Positive]=Field(default_factory=lambda:[300,300],min_length=1,max_length=10)
    clock_mode: ClockMode='clean'
    mixed_stop_last_s: Positive|None=None

    @model_validator(mode='after')
    def coherent(self):
        validate_mixed(self.clock_mode,self.mixed_stop_last_s,self.periods_s)
        return self


class Shootout(Input):
    enabled: bool=False
    initial_attempts: Positive=5


class Fouls(Input):
    enabled: bool=True
    warning_threshold: Positive=5
    reset: Literal['period','match']='period'
    extra_carry: bool=True


class Points(Input):
    win: Nonnegative=3
    draw: Nonnegative=1
    loss: Nonnegative=0


def validate_mixed(mode,window,periods):
    if mode=='mixed' and (window is None or window>min(periods)):
        raise ValueError('Интервал чистого времени должен помещаться в каждый тайм')


class Regulation(Input):
    periods_s: list[Positive]=Field(default_factory=lambda:[1200,1200],min_length=1,max_length=10)
    clock_mode: ClockMode='clean'
    mixed_stop_last_s: Positive|None=None
    clock_display: Literal['elapsed','remaining']='remaining'
    break_s: list[Nonnegative]=Field(default_factory=lambda:[600],max_length=9)
    schedule_slot_s: Positive=5400
    timeouts: Timeouts=Field(default_factory=Timeouts)
    extra: Extra=Field(default_factory=Extra)
    shootout: Shootout=Field(default_factory=Shootout)
    players_on_pitch: Annotated[int,Field(ge=1,le=1000)]=5
    tournament_roster_limit: Annotated[int,Field(ge=1,le=1000)]=30
    match_roster_limit: Annotated[int,Field(ge=1,le=1000)]=14
    pitch_length_m: float=Field(default=40,gt=0,le=300,allow_inf_nan=False)
    pitch_width_m: float=Field(default=20,gt=0,le=300,allow_inf_nan=False)
    fouls: Fouls=Field(default_factory=Fouls)
    points: Points=Field(default_factory=Points)
    allow_draw: bool=True

    @property
    def total_s(self): return sum(self.periods_s)

    @model_validator(mode='after')
    def coherent(self):
        if len(self.break_s)!=len(self.periods_s)-1:
            raise ValueError('Число перерывов должно быть на один меньше числа таймов')
        validate_mixed(self.clock_mode,self.mixed_stop_last_s,self.periods_s)
        if not self.players_on_pitch<=self.match_roster_limit<=self.tournament_roster_limit:
            raise ValueError('Лимиты заявки должны вмещать игроков на поле и заявку на матч')
        if self.timeouts.allowed and self.timeouts.count==0:
            raise ValueError('Укажите число разрешённых тайм-аутов')
        return self


class TournamentCreate(Input):
    request_id: UUID=Field(default_factory=uuid4)
    name: str=Field(min_length=1,max_length=200)
    season: str=Field(min_length=1,max_length=100)
    starts_on: date
    ends_on: date
    timezone: str='Europe/Moscow'
    visibility: Literal['draft','public']='draft'

    @model_validator(mode='after')
    def valid_dates(self):
        if self.ends_on<self.starts_on: raise ValueError('Окончание раньше начала')
        try: ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError,ValueError): raise ValueError('Неизвестный часовой пояс')
        return self


class TournamentPatch(Input):
    expected_revision: int=Field(ge=0)
    name: str|None=Field(default=None,min_length=1,max_length=200)
    season: str|None=Field(default=None,min_length=1,max_length=100)
    starts_on: date|None=None
    ends_on: date|None=None
    timezone: str|None=None
    archived: bool|None=None
    visibility: Literal['draft','public']|None=None
    standings_public: bool|None=None


class RegulationCreate(Input):
    request_id: UUID=Field(default_factory=uuid4)
    variant_name: str=Field(min_length=1,max_length=100)
    rules: Regulation
