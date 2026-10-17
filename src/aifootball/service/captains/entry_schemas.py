from uuid import UUID
from datetime import datetime
from pydantic import BaseModel,Field,field_validator
from aifootball.service.tournaments.schemas import Input
from aifootball.service.catalog.schemas import RosterPlayer
from aifootball.service.captains.schemas import ReasonCommand

class ApplicationCreate(Input):
    request_id:UUID
    team_id:UUID
    invitation_id:UUID|None=None
class ApplicationCommand(Input):
    request_id:UUID
    expected_revision:int=Field(ge=0,strict=True)
class ApplicationDraft(ApplicationCommand):
    source_roster_revision:int=Field(ge=0,strict=True)
    players:list[RosterPlayer]=Field(max_length=1000)
class ApplicationDecision(ApplicationCommand):
    reason:str=Field(min_length=1,max_length=1000)
    version_id:UUID|None=None
class ApplicationSettings(Input):
    request_id:UUID
    expected_revision:int=Field(ge=0,strict=True)
    applications_open:bool
    deadline:datetime|None=None
    @field_validator('deadline')
    @classmethod
    def aware(cls,value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):raise ValueError('Укажите часовой пояс срока подачи')
        return value
class EntryInvitationCreate(Input):
    request_id:UUID
    team_id:UUID
class ApplicationPlayer(BaseModel):
    player_id:UUID
    display_name:str
    shirt_number:str|None=None
class ApplicationPayload(BaseModel):
    source_roster_revision:int
    expected_entry_revision:int|None=None
    players:list[ApplicationPlayer]
class ApplicationVersionView(BaseModel):
    id:UUID
    number:int
    actor_id:UUID
    created_at:datetime
    payload:ApplicationPayload
class CaptainTournamentOption(BaseModel):
    id:UUID
    name:str
    season:str
    timezone:str='Europe/Moscow'
    archived:bool=False
    applications_open:bool
    deadline:datetime|None=None
    invitation_id:UUID|None=None
class ApplicationView(BaseModel):
    id:UUID
    tournament_id:UUID
    tournament:CaptainTournamentOption
    team_id:UUID
    team_name:str
    revision:int
    status:str
    reason:str
    draft:ApplicationPayload
    submitted_version:ApplicationVersionView|None=None
    accepted_version_id:UUID|None=None
    versions:list[ApplicationVersionView]=Field(default_factory=list)

class EntryInvitationView(BaseModel):
    id:UUID
    tournament_id:UUID
    team_id:UUID
    team_name:str
    active:bool
    created_at:datetime
