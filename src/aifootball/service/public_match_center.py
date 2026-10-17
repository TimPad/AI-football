"""Bounded guest calendar over the existing published match reader."""
import base64
import hashlib
import json
from datetime import date,datetime,time,timedelta,timezone
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import Depends,Query
from pydantic import BaseModel
from sqlalchemy import select,func,tuple_
from sqlalchemy.orm import Session
from aifootball.service.db import get_session
from aifootball.service.errors import DomainError
from aifootball.service.matches.models import Match
from aifootball.service.tournaments.models import Tournament
from aifootball.service.views import PublicMatch

ZONE=ZoneInfo('Europe/Moscow')
def now():return datetime.now(timezone.utc)

class PublicMatchDayPage(BaseModel):
    day:date
    timezone:str='Europe/Moscow'
    generated_at:datetime
    items:list[PublicMatch]
    total:int
    next_cursor:str|None
    tournament_totals:dict[str,int]

class PublicUpcomingMatches(BaseModel):
    timezone:str='Europe/Moscow'
    generated_at:datetime
    items:list[PublicMatch]

def register(router,match_query,match_view):
    @router.get('/matches',response_model=PublicMatchDayPage)
    def day_matches(day:date|None=None,status:Literal['all','live','upcoming','finished']='all',
                    tournament_id:UUID|None=None,team_id:UUID|None=None,q:str=Query('',max_length=200),
                    limit:int=Query(50,ge=1,le=100),cursor:str|None=Query(None,max_length=1500),db:Session=Depends(get_session)):
        generated=now();day=day or generated.astimezone(ZONE).date()
        start=datetime.combine(day,time.min,tzinfo=ZONE)
        query=match_query(tournament_id=tournament_id,team_id=team_id,q=q).where(Match.scheduled_at>=start,Match.scheduled_at<start+timedelta(days=1))
        if status!='all':query=query.where(Match.status=={'live':'live','upcoming':'scheduled','finished':'ended'}[status])
        if status=='upcoming':query=query.where(Match.scheduled_at>=generated)
        source=query.subquery();total=db.scalar(select(func.count()).select_from(source))
        fingerprint=hashlib.sha256(json.dumps([day.isoformat(),status,str(tournament_id),str(team_id),q],ensure_ascii=False).encode()).hexdigest()[:24]
        order=(func.lower(Tournament.name),Tournament.id,Match.scheduled_at,Match.id)
        if cursor:
            try:
                values=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if not isinstance(values,list) or len(values)!=5 or values[0]!=fingerprint or not isinstance(values[1],str) or len(values[1])>200:raise ValueError()
                query=query.where(tuple_(*order)>tuple_(values[1],UUID(values[2]),datetime.fromisoformat(values[3]),UUID(values[4])))
            except (ValueError,TypeError,KeyError,json.JSONDecodeError):
                raise DomainError('validation','Курсор не соответствует фильтрам. Начните выдачу сначала.',status=422)
        rows=db.execute(query.add_columns(order[0]).order_by(*order).limit(limit+1)).all();more=len(rows)>limit;rows=rows[:limit]
        group_ids={row[1].id for row in rows}
        counts=db.execute(select(source.c.tournament_id,func.count()).where(source.c.tournament_id.in_(group_ids)).group_by(source.c.tournament_id)).all() if group_ids else []
        next_cursor=None
        if more:
            m,t=rows[-1][:2]
            next_cursor=base64.urlsafe_b64encode(json.dumps([fingerprint,rows[-1][-1],str(t.id),m.scheduled_at.isoformat(),str(m.id)]).encode()).decode().rstrip('=')
        return {'day':day,'generated_at':generated,'items':[match_view(row[:-1]) for row in rows],'total':total,
                'next_cursor':next_cursor,'tournament_totals':{str(key):value for key,value in counts}}

    @router.get('/matches/upcoming',response_model=PublicUpcomingMatches)
    def upcoming(tournament_id:UUID|None=None,team_id:UUID|None=None,q:str=Query('',max_length=200),limit:int=Query(3,ge=1,le=3),db:Session=Depends(get_session)):
        generated=now()
        query=match_query(tournament_id=tournament_id,team_id=team_id,q=q).where(Match.status=='scheduled',Match.scheduled_at>=generated,Match.scheduled_at<=generated+timedelta(days=14))
        return {'generated_at':generated,'items':[match_view(row) for row in db.execute(query.order_by(Match.scheduled_at,Match.id).limit(limit))]}
