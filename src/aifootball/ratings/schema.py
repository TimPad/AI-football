from dataclasses import dataclass
import math
from uuid import UUID

ROLES={'goalkeeper','fixo','ala','pivot','universal','unknown'}
TIME_BASES={'reviewed_effective','official_clean','running_clock'}
COMPLETENESS={'complete','partial','unknown'}


def number(value,*,maximum=None):
    if type(value) not in (int,float) or not math.isfinite(value) or value<0 or (maximum is not None and value>maximum):
        raise ValueError('Expected a finite nonnegative number')


def uuid(value):
    if type(value) is not str or str(UUID(value))!=value:raise ValueError('Expected a canonical UUID')


@dataclass(frozen=True)
class MetricFact:
    value:float|None
    numerator:float|None
    denominator:float|None
    unit:str
    completeness:str
    reason:str|None

    def __post_init__(self):
        for value in (self.value,self.numerator,self.denominator):
            if value is not None:number(value)
        if type(self.completeness) is not str or self.completeness not in COMPLETENESS or type(self.unit) is not str or not self.unit:
            raise ValueError('Invalid metric metadata')
        if self.value is None and not self.reason:raise ValueError('Missing metric requires a reason')


@dataclass(frozen=True)
class MatchPerformance:
    tournament_id:str
    match_id:str
    player_id:str
    role:str
    time_basis:str
    eligible_play_s:float|None
    participation_s:float|None
    coverage:float|None
    facts:dict[str,MetricFact]
    provenance:dict

    def __post_init__(self):
        for value in (self.tournament_id,self.match_id,self.player_id):uuid(value)
        if type(self.role) is not str or self.role not in ROLES or type(self.time_basis) is not str or self.time_basis not in TIME_BASES:
            raise ValueError('Unknown role/time basis')
        for value in (self.eligible_play_s,self.participation_s):
            if value is not None:number(value)
        if self.coverage is not None:number(self.coverage,maximum=1)
