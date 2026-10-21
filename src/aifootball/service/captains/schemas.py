import re
from uuid import UUID,uuid4
from datetime import datetime
from pydantic import BaseModel,Field,field_validator
from aifootball.service.tournaments.schemas import Input

class EmailInput(Input):
    email:str=Field(min_length=3,max_length=254)
    @field_validator('email')
    @classmethod
    def normalize(cls,value):
        value=value.strip().casefold()
        if not re.fullmatch(r'[^\s@]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}',value) or '..' in value:raise ValueError('Укажите действительный email')
        return value
class Register(EmailInput):
    request_id:UUID=Field(default_factory=uuid4)
    display_name:str=Field(min_length=1,max_length=200)
    password:str=Field(min_length=12,max_length=200)
class Login(EmailInput):
    password:str=Field(min_length=1,max_length=200)
class TokenInput(Input):
    request_id:UUID=Field(default_factory=uuid4)
    token:str=Field(min_length=20,max_length=200)
class ResetComplete(TokenInput):
    password:str=Field(min_length=12,max_length=200)
class CaptainSessionView(BaseModel):
    id:UUID
    email:str
    display_name:str
    csrf_token:str
class MessageView(BaseModel):
    message:str
class InvitationCreate(EmailInput):
    request_id:UUID
class ReasonCommand(Input):
    request_id:UUID
    reason:str=Field(min_length=1,max_length=1000)
class GrantCreate(ReasonCommand):
    account_id:UUID
    replace:bool=False
class OwnershipRequest(Input):
    request_id:UUID
    team_id:UUID
    message:str=Field(default='',max_length=1000)
class GrantView(BaseModel):
    id:UUID
    account_id:UUID
    team_id:UUID
    active:bool
class InvitationView(BaseModel):
    id:UUID
    team_id:UUID
    email:str
    expires_at:datetime
    used_at:datetime|None=None
    revoked_at:datetime|None=None
