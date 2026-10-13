from datetime import timezone
from sqlalchemy import select,delete
from fastapi.encoders import jsonable_encoder
from aifootball.service.common import get_entity,as_dict
from aifootball.service.catalog.models import Entry,EntryPlayer,Player,Team
from aifootball.service.catalog.operations import entry_view
from aifootball.service.tournaments.models import Tournament,RegulationVersion
from aifootball.service.tournaments.schemas import Regulation
from aifootball.service.tournaments.rules import resolve_rules
from aifootball.service.matches.models import Match,LineupMember
from aifootball.service.protocol.schemas import ProtocolDocument,ClockState
from aifootball.service.errors import DomainError
from aifootball.service.db import utcnow


def assert_match_links(home,away,regulation,tournament_id):
    if home.id==away.id: raise DomainError('same_team','Команды матча должны отличаться')
    if {home.tournament_id,away.tournament_id,regulation.tournament_id}!={tournament_id}:
        raise DomainError('foreign_tournament','Выберите команды и регламент этого турнира')


def create_match(db,tid,data,actor):
    tournament=get_entity(db,Tournament,tid)
    home=get_entity(db,Entry,data.home_entry_id); away=get_entity(db,Entry,data.away_entry_id)
    regulation=get_entity(db,RegulationVersion,data.regulation_id)
    assert_match_links(home,away,regulation,tid)
    if tournament.archived or any(get_entity(db,Team,e.team_id).archived for e in [home,away]):
        raise DomainError('archived','Выбранная запись в архиве')
    if data.regulation_override and not data.override_reason:
        raise DomainError('override_reason','Объясните исключение из регламента')
    values=data.model_dump()
    values['regulation_override']=data.regulation_override.model_dump() if data.regulation_override else None
    values['scheduled_at']=data.scheduled_at.astimezone(timezone.utc)
    match=Match(tournament_id=tid,**values,protocol=ProtocolDocument().model_dump(mode='json'),clock=ClockState().model_dump(mode='json'))
    db.add(match); db.flush()
    return get_match_view(db,match.id)


def get_match_view(db,match_id):
    match=get_entity(db,Match,match_id)
    version=get_entity(db,RegulationVersion,match.regulation_id)
    rules=resolve_rules(match,version)
    lineup=[as_dict(item) for item in db.scalars(select(LineupMember).where(LineupMember.match_id==match.id).order_by(LineupMember.side.desc(),LineupMember.created_at,LineupMember.id))]
    projection={'event_score':{'home':0,'away':0},'effective_score':{'home':None,'away':None},
                'warnings':[],'incomplete_sections':list(match.protocol['completeness'])}
    try:
        from aifootball.service.protocol.projection import project_protocol
    except ModuleNotFoundError:
        pass  # Расчёт подключается следующим этапом; до этого нет событий.
    else:
        projection=project_protocol(ProtocolDocument.model_validate(match.protocol),rules).model_dump(mode='json')
    result={**as_dict(match),'match_id':match.id,'lineup':lineup,'projection':projection,
            'regulation':{**as_dict(version),'rules':rules.model_dump(),'total_s':rules.total_s},
            'home':entry_view(db,get_entity(db,Entry,match.home_entry_id)),
            'away':entry_view(db,get_entity(db,Entry,match.away_entry_id)),
            'server_now_ms':int(utcnow().timestamp()*1000)}
    return jsonable_encoder(result)


def set_lineup(db,match,data):
    version=get_entity(db,RegulationVersion,match.regulation_id); rules=resolve_rules(match,version)
    by_side={'home':[],'away':[]}; player_ids=[]; members=[]
    for item in data.players:
        ep=get_entity(db,EntryPlayer,item.entry_player_id)
        target=match.home_entry_id if item.side=='home' else match.away_entry_id
        player=get_entity(db,Player,ep.player_id)
        if ep.entry_id!=target or not ep.active or player.archived:
            raise DomainError('foreign_player','Выберите игрока из действующей заявки этой команды')
        player_ids.append(ep.player_id); by_side[item.side].append(ep.shirt_number)
        members.append(LineupMember(match_id=match.id,entry_player_id=ep.id,player_id=ep.player_id,
                                    side=item.side,shirt_number=ep.shirt_number,display_name=player.name))
    if len(player_ids)!=len(set(player_ids)): raise DomainError('duplicate_player','Игрок повторяется в составе')
    for numbers in by_side.values():
        if len(numbers)>rules.match_roster_limit: raise DomainError('roster_limit','Превышен размер состава')
        known=[n for n in numbers if n]
        if len(known)!=len(set(known)): raise DomainError('duplicate_number','Номер повторяется в составе')
    kept={str(p) for p in player_ids}
    for event in match.protocol['events']:
        for key in ['player_id','assist_id','victim_id','player_out_id','player_in_id']:
            if event.get(key) and event[key] not in kept:
                raise DomainError('referenced_player','Сначала исправьте события удаляемого игрока')
    old={row.player_id:row for row in db.scalars(select(LineupMember).where(LineupMember.match_id==match.id))}
    for member in members:
        previous=old.pop(member.player_id,None)
        if previous:
            if previous.side!=member.side: raise DomainError('side_change','Игрок уже включён в другую команду')
            # Сохраняем уже зафиксированные имя/номер при повторном выборе.
        else: db.add(member)
    for member in old.values(): db.delete(member)
    db.flush()
