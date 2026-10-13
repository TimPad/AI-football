from sqlalchemy import select
from aifootball.service.catalog.models import Team,Player,Entry,EntryPlayer
from aifootball.service.common import as_dict,get_entity
from aifootball.service.errors import DomainError,RevisionConflict
from aifootball.service.tournaments.models import Tournament,RegulationVersion


def entry_view(db,entry):
    return {**as_dict(entry),'team':as_dict(get_entity(db,Team,entry.team_id))}


def roster_view(db,entry):
    rows=db.scalars(select(EntryPlayer).where(EntryPlayer.entry_id==entry.id,EntryPlayer.active).order_by(EntryPlayer.created_at)).all()
    return {**entry_view(db,entry),'players':[{**as_dict(row),'player':as_dict(get_entity(db,Player,row.player_id))} for row in rows]}


def set_roster(db,entry,data):
    if entry.revision!=data.expected_revision: raise RevisionConflict(entry.revision)
    tournament=get_entity(db,Tournament,entry.tournament_id)
    if tournament.archived: raise DomainError('archived','Турнир в архиве')
    ids=[p.player_id for p in data.players]
    numbers=[p.shirt_number for p in data.players if p.shirt_number]
    if len(ids)!=len(set(ids)) or len(numbers)!=len(set(numbers)):
        raise DomainError('duplicate_roster','Игрок или номер повторяется в заявке')
    rules=db.scalar(select(RegulationVersion).where(RegulationVersion.tournament_id==entry.tournament_id).order_by(RegulationVersion.created_at.desc()))
    if rules and len(ids)>rules.rules['tournament_roster_limit']:
        raise DomainError('roster_limit','Превышен размер заявки турнира')
    old={p.player_id:p for p in db.scalars(select(EntryPlayer).where(EntryPlayer.entry_id==entry.id))}
    for item in old.values(): item.active=False
    db.flush()  # Освободить номера перед их изменением.
    for item in data.players:
        player=get_entity(db,Player,item.player_id)
        if player.archived: raise DomainError('archived','Игрок в архиве')
        row=old.get(item.player_id)
        if row is None:
            row=EntryPlayer(entry_id=entry.id,player_id=item.player_id); db.add(row)
        row.shirt_number=item.shirt_number or None; row.active=True
    entry.revision+=1
    db.flush()
    return roster_view(db,entry)
