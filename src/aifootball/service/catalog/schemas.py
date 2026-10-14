from uuid import UUID,uuid4
from datetime import date
from typing import Literal
from pydantic import Field,field_validator
from aifootball.service.tournaments.schemas import Input


class NamedCreate(Input):
    name:str=Field(min_length=1,max_length=200)


class NamedPatch(Input):
    name:str|None=Field(default=None,min_length=1,max_length=200)
    archived:bool|None=None


class PlayerDetails(Input):
    photo_id:UUID|None=None
    birth_date:date|None=None
    position:Literal['goalkeeper','defender','winger','forward','universal']|None=None
    height_cm:int|None=Field(default=None,ge=50,le=250,strict=True)
    weight_kg:float|None=Field(default=None,gt=0,le=300,allow_inf_nan=False)

    @field_validator('birth_date')
    @classmethod
    def not_future(cls,value):
        if value is not None and value>date.today(): raise ValueError('Дата рождения не может быть в будущем')
        return value


class PlayerCreate(NamedCreate,PlayerDetails): pass
class PlayerPatch(NamedPatch,PlayerDetails): pass


class ProfilePlayer(PlayerDetails):
    player_id:UUID
    revision:int=Field(default=0,ge=0)
    name:str=Field(min_length=1,max_length=200)
    shirt_number:str|None=Field(default=None,max_length=10)


class TeamCreate(NamedCreate):
    request_id:UUID=Field(default_factory=uuid4)
    description:str=Field(default='',max_length=4000)
    logo_id:UUID|None=None
    players:list[ProfilePlayer]=Field(default_factory=list,max_length=1000)


class TeamProfileUpdate(TeamCreate):
    expected_revision:int=Field(ge=0)


class TeamPatch(NamedPatch):
    description:str|None=Field(default=None,max_length=4000)
    logo_id:UUID|None=None


class EntryCreate(Input):
    team_id:UUID


class RosterPlayer(Input):
    player_id:UUID
    shirt_number:str|None=Field(default=None,max_length=10)


class RosterUpdate(Input):
    expected_revision:int=Field(ge=0)
    players:list[RosterPlayer]=Field(max_length=1000)
