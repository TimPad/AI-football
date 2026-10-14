from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import Field,field_validator
from urllib.parse import urlsplit,parse_qs
import re
from aifootball.service.tournaments.schemas import Input,Regulation

MatchStatus=Literal['scheduled','live','ended','postponed','cancelled']


class BroadcastFields(Input):
    broadcast_url:str|None=Field(default=None,max_length=2048)
    broadcast_embed_url:str|None=Field(default=None,max_length=2048)

    @field_validator('broadcast_url','broadcast_embed_url')
    @classmethod
    def vk_url(cls,value,info):
        if value is None or not value.strip(): return None
        value=value.strip()
        try:
            url=urlsplit(value)
            valid=url.scheme=='https' and url.hostname in {'vk.com','www.vk.com','vkvideo.ru','www.vkvideo.ru'} and not url.username and not url.password and url.port in {None,443}
        except ValueError:
            valid=False
        if not valid: raise ValueError('Используйте HTTPS-ссылку на VK или VK Видео')
        if info.field_name=='broadcast_embed_url':
            params=parse_qs(url.query)
            if url.path!='/video_ext.php' or not re.fullmatch(r'-?\d+',params.get('oid',[''])[0]) or not re.fullmatch(r'\d+',params.get('id',[''])[0]):
                raise ValueError('Укажите src из iframe ВК: video_ext.php с oid и id')
        return value


class MatchCreate(BroadcastFields):
    hall_id:UUID
    camera_profile_id:UUID|None=None
    home_entry_id:UUID
    away_entry_id:UUID
    regulation_id:UUID
    scheduled_at:datetime
    venue_label:str=Field(default='',max_length=200)
    referees:list[str]=Field(default_factory=list,max_length=10)
    regulation_override:Regulation|None=None
    override_reason:str|None=Field(default=None,max_length=2000)

    @field_validator('scheduled_at')
    @classmethod
    def aware(cls,value):
        if value is None or value.tzinfo is None: raise ValueError('Дата матча должна содержать часовой пояс')
        return value


class MatchUpdate(BroadcastFields):
    hall_id:UUID|None=None
    camera_profile_id:UUID|None=None
    scheduled_at:datetime|None=None
    venue_label:str|None=Field(default=None,max_length=200)
    referees:list[str]|None=Field(default=None,max_length=10)
    regulation_override:Regulation|None=None
    override_reason:str|None=Field(default=None,max_length=2000)
    _aware=field_validator('scheduled_at')(MatchCreate.aware.__func__)


class LineupSelection(Input):
    entry_player_id:UUID
    side:Literal['home','away']


class LineupUpdate(Input):
    players:list[LineupSelection]=Field(max_length=2000)


class StatusUpdate(Input):
    status:MatchStatus


class ApplyMatch(Input):
    id:UUID
    expected_revision:int=Field(ge=0)


class PreviewRules(Input):
    match_ids:list[UUID]=Field(min_length=1,max_length=100)


class ApplyRules(Input):
    request_id:UUID
    matches:list[ApplyMatch]=Field(min_length=1,max_length=100)
