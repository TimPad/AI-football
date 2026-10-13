from uuid import UUID
from pydantic import Field
from aifootball.service.tournaments.schemas import Input


class NamedCreate(Input):
    name:str=Field(min_length=1,max_length=200)


class NamedPatch(Input):
    name:str|None=Field(default=None,min_length=1,max_length=200)
    archived:bool|None=None


class EntryCreate(Input):
    team_id:UUID


class RosterPlayer(Input):
    player_id:UUID
    shirt_number:str|None=Field(default=None,max_length=10)


class RosterUpdate(Input):
    expected_revision:int=Field(ge=0)
    players:list[RosterPlayer]=Field(max_length=1000)
