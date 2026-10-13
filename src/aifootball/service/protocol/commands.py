import json
from hashlib import sha256
from pydantic import ValidationError
from sqlalchemy import select
from aifootball.service.errors import DomainError,RevisionConflict
from aifootball.service.common import get_entity
from aifootball.service.matches.models import Match,MatchCommand
from aifootball.service.matches.schemas import MatchUpdate,LineupUpdate,StatusUpdate
from aifootball.service.matches.operations import get_match_view,set_lineup
from aifootball.service.tournaments.schemas import Regulation


def validate_payload(cls,value):
    try: return cls.model_validate(value)
    except ValidationError as error:
        raise DomainError('validation','Проверьте поля формы',
            {'.'.join(map(str,e['loc'])):e['msg'] for e in error.errors()}) from error


def request_digest(command):
    return sha256(json.dumps(command.model_dump(mode='json'),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def apply_mutation(db,match,command,actor):
    if not match.protocol.get('draft',True) and command.kind not in ['reopen','publish','unpublish']:
        raise DomainError('confirmed','Сначала откройте новую редакцию протокола')
    if command.kind=='update_match':
        data=validate_payload(MatchUpdate,command.payload)
        values=data.model_dump(exclude_unset=True)
        if values.get('regulation_override') is not None and not values.get('override_reason',match.override_reason):
            raise DomainError('override_reason','Объясните исключение из регламента')
        if 'regulation_override' in values and match.protocol['events']:
            raise DomainError('started_match','Нельзя заменить регламент матча с событиями')
        for key,value in values.items():
            if value is None and key in ['venue_label','scheduled_at','referees']:
                raise DomainError('validation','Не очищайте обязательные поля')
            setattr(match,key,value)
    elif command.kind=='set_lineup':
        set_lineup(db,match,validate_payload(LineupUpdate,command.payload))
    elif command.kind=='set_status':
        data=validate_payload(StatusUpdate,command.payload)
        allowed={'scheduled':{'live','ended','postponed','cancelled'},'live':{'ended','cancelled','postponed'},
                 'ended':{'scheduled'},'postponed':{'scheduled'},'cancelled':{'scheduled'}}
        if data.status!=match.status and data.status not in allowed[match.status]:
            raise DomainError('status_transition','Недопустимый переход статуса матча')
        match.status=data.status
    else:
        from aifootball.service.protocol.mutations import apply_protocol_mutation
        apply_protocol_mutation(db,match,command,actor)


def record_command(db,match,command,actor,mutation=None):
    digest=request_digest(command)
    old=db.scalar(select(MatchCommand).where(MatchCommand.match_id==match.id,MatchCommand.request_id==command.request_id))
    if old:
        if old.request_hash!=digest: raise DomainError('idempotency_conflict','Ключ отправки уже использован',status=409)
        return old.response
    if match.revision!=command.expected_revision: raise RevisionConflict(match.revision)
    (mutation or apply_mutation)(db,match,command,actor)
    match.revision+=1; db.flush()
    result=get_match_view(db,match.id)
    db.add(MatchCommand(match_id=match.id,actor_id=actor.id,request_id=command.request_id,request_hash=digest,
        before_revision=command.expected_revision,after_revision=match.revision,
        body=command.model_dump(mode='json'),response=result))
    return result


def execute_command(db,match_id,command,actor):
    with db.begin():
        return record_command(db,get_entity(db,Match,match_id,lock=True),command,actor)
