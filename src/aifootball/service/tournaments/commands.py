"""Serialize setup mutations and replay their exact committed response."""
import json
from hashlib import sha256
from sqlalchemy import select, func
from fastapi.encoders import jsonable_encoder
from aifootball.service.errors import DomainError, RevisionConflict
from aifootball.service.common import get_entity
from aifootball.service.tournaments.models import Tournament, SetupCommand


def setup_command(db, actor_id, request_id, kind, payload, execute):
    db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(request_id.bytes[:8], signed=True))))
    digest = sha256(json.dumps(jsonable_encoder(payload), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    prior = db.scalar(select(SetupCommand).where(SetupCommand.request_id == request_id))
    if prior is not None:
        if prior.actor_id != actor_id or prior.kind != kind or prior.request_hash != digest:
            raise DomainError('idempotency_conflict', 'Ключ сохранения уже использован для других данных', status=409)
        return prior.response
    result = jsonable_encoder(execute())
    db.add(SetupCommand(actor_id=actor_id, request_id=request_id, kind=kind, request_hash=digest, response=result))
    db.flush()
    return result


def editable_tournament(db, tournament_id, expected_revision):
    tournament = get_entity(db, Tournament, tournament_id, lock=True)
    if tournament.archived:
        raise DomainError('archived', 'Турнир в архиве')
    if tournament.revision != expected_revision:
        raise RevisionConflict(tournament.revision)
    return tournament
