"""Apply a reviewed import in one transaction, preserving unrelated data."""
from collections import defaultdict
from hashlib import sha256
from uuid import UUID
from sqlalchemy import select, func
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.catalog.models import Team, Player, TeamMember, Entry, EntryPlayer
from aifootball.service.catalog.schemas import ProfilePlayer, RosterUpdate, RosterPlayer
from aifootball.service.catalog.operations import set_roster
from .models import RosterImport
from .preview import owned_import, target_entity, import_view


def conflict():
    raise DomainError('import_conflict', 'Данные изменились после проверки. Обновите предпросмотр: ввод сохранён.', status=409)


def apply_import(db, identifier, actor_id, data, actor_kind='admin'):
    db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(data.request_id.bytes[:8], signed=True))))
    session = owned_import(db, identifier, actor_id, actor_kind, lock=True)
    if session.status == 'committed':
        if session.commit_request_id == data.request_id and session.commit_revision == data.expected_revision:
            return session.result
        raise DomainError('already_committed', 'Импорт уже применён. Откройте его результат.', status=409)
    if session.revision != data.expected_revision:
        conflict()
    if not import_view(session)['can_commit']:
        raise DomainError('import_errors', 'Исправьте ошибки или явно исключите строки перед применением')
    if db.scalar(select(RosterImport.id).where(RosterImport.commit_request_id == data.request_id)):
        raise DomainError('idempotency_conflict', 'Ключ применения уже использован', status=409)
    active = [row for row in session.rows if not row['excluded']]
    expected = session.expected
    # Name locks prevent two previews from silently creating the same new candidate concurrently.
    names = [(kind, name) for kind in ('new_player_candidates', 'new_team_candidates') for name in expected[kind]]
    for kind, name in sorted(names):
        key = int.from_bytes(sha256((kind + ':' + name).encode()).digest()[:8], signed=True)
        db.execute(select(func.pg_advisory_xact_lock(key)))
    target = target_entity(db, session.scope, session.target_id)
    db.refresh(target, with_for_update=True)
    if target.revision != expected['target_revision'] or target.archived:
        conflict()
    for field, cls in (('teams', Team), ('players', Player), ('entries', Entry)):
        for key, revision in sorted(expected[field].items()):
            entity = db.scalar(select(cls).where(cls.id == UUID(key)).with_for_update())
            if entity is None or entity.revision != revision or getattr(entity, 'archived', False):
                conflict()
    for key, cls in (('new_player_candidates', Player), ('new_team_candidates', Team)):
        for name, previous in expected[key].items():
            found = sorted(str(value) for value in db.scalars(select(cls.id).where(func.lower(cls.name) == name)))
            if found != previous:
                conflict()
    groups = defaultdict(list)
    for row in active:
        groups[row['team_id']].append(row)
    for row in active:
        if row['is_new_player']:
            profile = ProfilePlayer(player_id=row['player_id'], name=row['name'], **row['details'])
            values = profile.model_dump(exclude={'player_id', 'revision', 'shirt_number'})
            db.add(Player(id=profile.player_id, **values))
    db.flush()
    links = []
    for team_id, rows in groups.items():
        team = db.get(Team, UUID(team_id))
        if team is None:
            team = Team(id=UUID(team_id), name=rows[0]['team_name'])
            db.add(team); db.flush()
        if session.scope == 'team':
            old = {str(member.player_id): member for member in db.scalars(select(TeamMember)
                .where(TeamMember.team_id == team.id))}
            for row in rows:
                member = old.get(row['player_id'])
                if member is None:
                    member = TeamMember(team_id=team.id, player_id=UUID(row['player_id']))
                    db.add(member)
                member.active = True
                member.shirt_number = row['shirt_number'] or member.shirt_number
            team.revision += 1
            links.append({'team_id': team_id, 'label': team.name, 'path': f'{"/captain" if actor_kind=="captain" else ""}/teams/{team_id}'})
        else:
            entry = db.scalar(select(Entry).where(Entry.tournament_id == target.id, Entry.team_id == team.id))
            if entry is not None and str(entry.id) not in expected['entries']:
                conflict()
            if entry is None:
                entry = Entry(tournament_id=target.id, team_id=team.id)
                db.add(entry); db.flush()
            previous = {str(member.player_id): member.shirt_number for member in db.scalars(select(EntryPlayer)
                .where(EntryPlayer.entry_id == entry.id, EntryPlayer.active))}
            for row in rows:
                previous[row['player_id']] = row['shirt_number'] or previous.get(row['player_id'])
            set_roster(db, entry, RosterUpdate(expected_revision=entry.revision, players=[
                RosterPlayer(player_id=identifier, shirt_number=number) for identifier, number in previous.items()]))
            links.append({'team_id': team_id, 'entry_id': str(entry.id), 'label': team.name,
                          'path': f'/tournaments/{target.id}/teams/{entry.id}'})
    session.result = {key: value for key, value in session.summary.items() if key != 'errors'} | {'links': links}
    session.status = 'committed'
    session.commit_request_id = data.request_id
    session.commit_revision = data.expected_revision
    session.revision += 1
    db.flush()
    return session.result
