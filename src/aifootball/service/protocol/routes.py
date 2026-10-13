from uuid import UUID
from fastapi import APIRouter,Depends,Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from aifootball.service.auth.security import require_admin
from aifootball.service.common import as_dict,get_entity,list_entities
from aifootball.service.db import get_session
from aifootball.service.errors import DomainError
from aifootball.service.matches.models import Match,MatchCommand
from aifootball.service.protocol.models import ProtocolVersion

router=APIRouter()


@router.get('/matches/{mid}/history',dependencies=[Depends(require_admin)])
def history(mid:UUID,db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    get_entity(db,Match,mid)
    result=list_entities(db,MatchCommand,where=[MatchCommand.match_id==mid],limit=limit,offset=offset,
                         order=MatchCommand.after_revision.desc())
    for row in result['items']: row.pop('response'); row.pop('request_hash')
    return result


@router.get('/matches/{mid}/versions',dependencies=[Depends(require_admin)])
def versions(mid:UUID,db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    get_entity(db,Match,mid)
    return list_entities(db,ProtocolVersion,where=[ProtocolVersion.match_id==mid],limit=limit,offset=offset,order=ProtocolVersion.number.desc())


@router.get('/public/protocols/{public_id}')
def public_protocol(public_id:UUID,db:Session=Depends(get_session)):
    version=db.scalar(select(ProtocolVersion).join(Match,Match.published_version_id==ProtocolVersion.id).where(ProtocolVersion.public_id==public_id))
    if version is None: raise DomainError('not_found','Опубликованный протокол не найден',status=404)
    source=version.snapshot
    events=[]
    for event in source['protocol']['events']:
        events.append({key:value for key,value in event.items() if key not in ['notes','created_at','video_ms']})
    return {'number':version.number,'confirmed_at':version.confirmed_at,'published_at':version.published_at,
        'home_name':source['home']['team']['name'],'away_name':source['away']['team']['name'],
        'scheduled_at':source['scheduled_at'],'venue_label':source['venue_label'],
        'regulation':{'rules':source['regulation']['rules'],'total_s':source['regulation']['total_s']},
        'lineup':[{key:row[key] for key in ['player_id','display_name','shirt_number','side']} for row in source['lineup']],
        'protocol':{key:value for key,value in source['protocol'].items() if key not in ['notes','attachment_ids']}
            | {'events':events},'projection':source['projection']}
