"""Atomic team sheets; player UUIDs survive roster and profile changes."""
import json
from hashlib import sha256
from uuid import uuid5, NAMESPACE_URL
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func
from aifootball.service.common import get_entity, as_dict
from aifootball.service.catalog.models import Team, Player, TeamMember, TeamProfileCommand, CatalogImage
from aifootball.service.catalog.schemas import PlayerDetails
from aifootball.service.errors import DomainError, RevisionConflict


def team_profile(db, team):
    members = db.execute(select(TeamMember, Player).join(Player, TeamMember.player_id == Player.id)
        .where(TeamMember.team_id == team.id, TeamMember.active)
        .order_by(TeamMember.created_at, TeamMember.id))
    return {**as_dict(team), 'players': [{**as_dict(member), 'player': as_dict(player)} for member, player in members]}


def check_image(db, identifier):
    if identifier is not None: get_entity(db, CatalogImage, identifier)


def save_profile(db, data, team_id=None):
    # Serialize equal request IDs even before a new team exists.
    db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(data.request_id.bytes[:8], signed=True))))
    digest = sha256(json.dumps({'team_id': str(team_id) if team_id else None, 'body': data.model_dump(mode='json')},
                              sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    prior = db.scalar(select(TeamProfileCommand).where(TeamProfileCommand.request_id == data.request_id))
    if prior:
        if prior.request_hash != digest:
            raise DomainError('idempotency_conflict', 'Ключ сохранения уже использован для других данных', status=409)
        return prior.response
    if team_id:
        team = get_entity(db, Team, team_id, lock=True)
        if team.revision != data.expected_revision: raise RevisionConflict(team.revision)
    else:
        team = Team(id=uuid5(NAMESPACE_URL, 'aifootball:team:' + str(data.request_id)), name=data.name)
        db.add(team); db.flush()
    if team.archived: raise DomainError('archived', 'Сначала восстановите команду из архива')
    ids = [row.player_id for row in data.players]
    numbers = [row.shirt_number for row in data.players if row.shirt_number]
    if len(ids) != len(set(ids)) or len(numbers) != len(set(numbers)):
        raise DomainError('duplicate_roster', 'Игрок или номер повторяется в составе команды')
    check_image(db, data.logo_id)
    old = {row.player_id: row for row in db.scalars(select(TeamMember).where(TeamMember.team_id == team.id))}
    for row in old.values(): row.active = False
    db.flush()  # Release numbers before swapping them.
    for row in sorted(data.players, key=lambda p: str(p.player_id)):
        person = db.scalar(select(Player).where(Player.id == row.player_id).with_for_update())
        values = {key: getattr(row, key) for key in PlayerDetails.model_fields} | {'name': row.name}
        check_image(db, row.photo_id)
        if person is None:
            if row.revision != 0: raise DomainError('player_missing', 'Игрок больше не доступен', status=409)
            person = Player(id=row.player_id, **values); db.add(person); db.flush()
        else:
            if person.archived: raise DomainError('archived', f'Игрок {person.name} находится в архиве')
            if person.revision != row.revision:
                raise DomainError('player_conflict', f'Данные игрока {person.name} изменились. Обновите карточку команды.', status=409)
            if any(getattr(person, key) != value for key, value in values.items()):
                for key, value in values.items(): setattr(person, key, value)
                person.revision += 1
        member = old.get(row.player_id)
        if member is None:
            member = TeamMember(team_id=team.id, player_id=person.id); db.add(member)
        member.shirt_number = row.shirt_number or None; member.active = True
    team.name = data.name; team.description = data.description; team.logo_id = data.logo_id; team.revision += 1
    db.flush()
    result = jsonable_encoder(team_profile(db, team))
    db.add(TeamProfileCommand(team_id=team.id, request_id=data.request_id, request_hash=digest, response=result))
    return result
