from datetime import datetime,date,time,timedelta,timezone
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import APIRouter,Depends,Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from aifootball.service.auth.security import require_admin,require_csrf
from aifootball.service.common import get_entity,list_entities,as_dict
from aifootball.service.db import get_session,utcnow
from aifootball.service.matches.models import Match
from aifootball.service.matches.schemas import MatchCreate,PreviewRules,ApplyRules
from aifootball.service.matches.operations import create_match,get_match_view
from aifootball.service.protocol.schemas import Command
from aifootball.service.protocol.command_schemas import CommandRequest
from aifootball.service.protocol.commands import execute_command,record_command
from aifootball.service.tournaments.models import Tournament,RegulationVersion
from aifootball.service.errors import DomainError

from aifootball.service.views import Page,MatchView

router=APIRouter()


@router.post('/tournaments/{tid}/matches',response_model=MatchView,status_code=201)
def new_match(tid:UUID,data:MatchCreate,db:Session=Depends(get_session),actor=Depends(require_csrf)):
    with db.begin(): return create_match(db,tid,data,actor)


@router.get('/tournaments/{tid}/matches',response_model=Page[MatchView],dependencies=[Depends(require_admin)])
def calendar(tid:UUID,day:date|None=None,db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    tournament=get_entity(db,Tournament,tid); where=[Match.tournament_id==tid]
    if day:
        zone=ZoneInfo(tournament.timezone)
        start=datetime.combine(day,time.min,tzinfo=zone); end=datetime.combine(day+timedelta(days=1),time.min,tzinfo=zone)
        where += [Match.scheduled_at>=start,Match.scheduled_at<end]
    result=list_entities(db,Match,where=where,order=Match.scheduled_at,limit=limit,offset=offset)
    result['items']=[get_match_view(db,row['id']) for row in result['items']]
    return result


@router.get('/matches/{mid}',response_model=MatchView,dependencies=[Depends(require_admin)])
def detail(mid:UUID,db:Session=Depends(get_session)): return get_match_view(db,mid)


@router.post('/matches/{mid}/commands',response_model=MatchView)
def command(mid:UUID,data:CommandRequest,db:Session=Depends(get_session),actor=Depends(require_csrf)):
    return execute_command(db,mid,data,actor)


def eligible(match):
    if match.status!='scheduled' or match.scheduled_at<=utcnow() or match.protocol['events'] or not match.protocol['draft'] or match.clock['phase']!='not_started':
        raise DomainError('started_match','Можно обновить только будущий матч без событий и запущенных часов')


@router.post('/tournaments/{tid}/regulations/{rid}/preview',dependencies=[Depends(require_csrf)])
def preview(tid:UUID,rid:UUID,data:PreviewRules,db:Session=Depends(get_session)):
    version=get_entity(db,RegulationVersion,rid)
    if version.tournament_id!=tid: raise DomainError('foreign_regulation','Регламент другого турнира')
    items=[]
    for mid in data.match_ids:
        match=get_entity(db,Match,mid)
        if match.tournament_id!=tid: raise DomainError('foreign_match','Матч другого турнира')
        reason=None
        try: eligible(match)
        except DomainError as error: reason=error.message
        items.append({'id':str(mid),'revision':match.revision,'before':get_match_view(db,mid)['regulation'],
                      'after':as_dict(version),'reason':reason})
    return {'items':items,'total':len(items)}


@router.post('/tournaments/{tid}/regulations/{rid}/apply',response_model=Page[MatchView])
def apply_rules(tid:UUID,rid:UUID,data:ApplyRules,db:Session=Depends(get_session),actor=Depends(require_csrf)):
    with db.begin():
        version=get_entity(db,RegulationVersion,rid)
        if version.tournament_id!=tid: raise DomainError('foreign_regulation','Регламент другого турнира')
        if len({m.id for m in data.matches})!=len(data.matches): raise DomainError('duplicate_match','Матч повторяется')
        results=[]
        def mutation(db,match,command,actor):
            if match.tournament_id!=tid: raise DomainError('foreign_match','Матч другого турнира')
            eligible(match); match.regulation_id=rid; match.regulation_override=None; match.override_reason=None
        for item in sorted(data.matches,key=lambda x:str(x.id)):
            match=get_entity(db,Match,item.id,lock=True)
            command=Command(request_id=data.request_id,expected_revision=item.expected_revision,kind='apply_regulation',
                payload={'regulation_id':str(rid),'batch':data.model_dump(mode='json')})
            results.append(record_command(db,match,command,actor,mutation))
    return {'items':results,'total':len(results)}
