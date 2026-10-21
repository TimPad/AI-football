"""Guest identities are projections of currently published protocol snapshots only."""
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter,Depends,Query
from pydantic import BaseModel
from sqlalchemy import select,func,case,cast,String,true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session,aliased
from aifootball.service.db import get_session
from aifootball.service.common import as_dict
from aifootball.service.errors import DomainError
from aifootball.service.public_visibility import require_public_tournament
from aifootball.service.catalog.models import Team,Entry
from aifootball.service.matches.models import Match
from aifootball.service.tournaments.models import Tournament
from aifootball.service.protocol.models import ProtocolVersion
from aifootball.service.views import Page,PublicTournament

router=APIRouter(prefix='/public')
class PublicTeamSummary(BaseModel):
    id:UUID
    name:str
    logo_id:UUID|None=None
class PublicRosterPlayer(BaseModel):
    player_id:UUID
    display_name:str
    shirt_number:str|None=None
    last_match_id:UUID
    last_published_at:datetime
class PublicTeamView(PublicTeamSummary):
    tournament:PublicTournament
    players:Page[PublicRosterPlayer]
class PublicAppearance(BaseModel):
    match_id:UUID
    protocol_public_id:UUID
    tournament_id:UUID
    tournament_name:str
    timezone:str
    team_id:UUID
    team_name:str
    display_name:str
    shirt_number:str|None=None
    scheduled_at:datetime
    published_at:datetime
class PublicPlayerTeam(BaseModel):
    team_id:UUID
    team_name:str
    tournament_id:UUID
    tournament_name:str
class PublicPlayerProfile(BaseModel):
    id:UUID
    display_name:str
    tournament_id:UUID|None=None
    teams:Page[PublicPlayerTeam]
    appearances:Page[PublicAppearance]

def appearances_query(*,tid=None,pid=None,team_id=None):
    he,ae=aliased(Entry),aliased(Entry)
    people=func.jsonb_array_elements(ProtocolVersion.snapshot['lineup']).table_valued('value').alias('published_person')
    p=cast(people.c.value,JSONB);side=p['side'].as_string()
    team=case((side=='home',he.team_id),else_=ae.team_id)
    team_name=case((side=='home',ProtocolVersion.snapshot['home']['team']['name'].as_string()),else_=ProtocolVersion.snapshot['away']['team']['name'].as_string())
    q=select(Match.id.label('match_id'),ProtocolVersion.id.label('source_version_id'),ProtocolVersion.public_id.label('protocol_public_id'),
        Tournament.id.label('tournament_id'),Tournament.name.label('tournament_name'),Tournament.timezone,
        team.label('team_id'),team_name.label('team_name'),p['player_id'].as_string().label('player_id'),p['display_name'].as_string().label('display_name'),
        p['shirt_number'].as_string().label('shirt_number'),Match.scheduled_at,ProtocolVersion.published_at)
    q=q.select_from(Match).join(Tournament,Match.tournament_id==Tournament.id).join(ProtocolVersion,Match.published_version_id==ProtocolVersion.id).join(he,Match.home_entry_id==he.id).join(ae,Match.away_entry_id==ae.id).join(people,true()).where(
        Tournament.visibility=='public',~Tournament.archived,ProtocolVersion.public_id.is_not(None),ProtocolVersion.published_at.is_not(None),side.in_(['home','away']))
    if tid:q=q.where(Tournament.id==tid)
    if pid:q=q.where(p['player_id'].as_string()==str(pid))
    if team_id:q=q.where(team==team_id)
    return q

def summary(team):return {'id':team.id,'name':team.name,'logo_id':team.logo_id}

@router.get('/tournaments/{tid}/teams',response_model=Page[PublicTeamSummary])
def public_teams(tid:UUID,limit:int=Query(default=50,ge=1,le=100),offset:int=Query(default=0,ge=0),db:Session=Depends(get_session)):
    require_public_tournament(db,tid)
    q=select(Team).join(Entry,Entry.team_id==Team.id).where(Entry.tournament_id==tid)
    return {'items':[summary(t) for t in db.scalars(q.order_by(Team.name,Team.id).offset(offset).limit(limit))],'total':db.scalar(select(func.count()).select_from(q.subquery()))}

@router.get('/tournaments/{tid}/teams/{team_id}',response_model=PublicTeamView)
def public_team(tid:UUID,team_id:UUID,limit:int=Query(default=50,ge=1,le=100),offset:int=Query(default=0,ge=0),db:Session=Depends(get_session)):
    tournament=require_public_tournament(db,tid);team=db.scalar(select(Team).join(Entry,Entry.team_id==Team.id).where(Entry.tournament_id==tid,Team.id==team_id))
    if team is None:raise DomainError('not_found','Команда не найдена в этом турнире',status=404)
    source=appearances_query(tid=tid,team_id=team_id).subquery()
    ranked=select(source,func.row_number().over(partition_by=source.c.player_id,order_by=(source.c.published_at.desc(),source.c.source_version_id.desc())).label('rank')).subquery()
    total=db.scalar(select(func.count()).select_from(ranked).where(ranked.c.rank==1))
    rows=db.execute(select(ranked).where(ranked.c.rank==1).order_by(ranked.c.display_name,ranked.c.player_id).offset(offset).limit(limit)).mappings()
    players=[{'player_id':r['player_id'],'display_name':r['display_name'],'shirt_number':r['shirt_number'],'last_match_id':r['match_id'],'last_published_at':r['published_at']} for r in rows]
    return summary(team)|{'tournament':as_dict(tournament),'players':{'items':players,'total':total}}

@router.get('/players/{player_id}',response_model=PublicPlayerProfile)
def public_player(player_id:UUID,tournament_id:UUID|None=None,limit:int=Query(default=50,ge=1,le=100),offset:int=Query(default=0,ge=0),teams_offset:int=Query(default=0,ge=0),db:Session=Depends(get_session)):
    if tournament_id:require_public_tournament(db,tournament_id)
    source=appearances_query(tid=tournament_id,pid=player_id).subquery()
    order=(source.c.published_at.desc(),source.c.source_version_id.desc())
    latest=db.execute(select(source.c.display_name).order_by(*order).limit(1)).first()
    if latest is None:raise DomainError('not_found','У игрока пока нет опубликованного состава в этом контексте',status=404)
    total=db.scalar(select(func.count()).select_from(source))
    rows=[dict(r) for r in db.execute(select(source).order_by(*order).offset(offset).limit(limit)).mappings()]
    teams=select(source,func.row_number().over(partition_by=(source.c.team_id,source.c.tournament_id),order_by=order).label('rank')).subquery()
    teams_total=db.scalar(select(func.count()).select_from(teams).where(teams.c.rank==1))
    teams_rows=[dict(r) for r in db.execute(select(teams.c.team_id,teams.c.team_name,teams.c.tournament_id,teams.c.tournament_name).where(teams.c.rank==1).order_by(teams.c.tournament_name,teams.c.team_name,teams.c.team_id).offset(teams_offset).limit(100)).mappings()]
    return {'id':player_id,'display_name':latest[0],'tournament_id':tournament_id,'teams':{'items':teams_rows,'total':teams_total},'appearances':{'items':rows,'total':total}}
