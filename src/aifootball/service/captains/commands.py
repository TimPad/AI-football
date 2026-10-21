import json
from hashlib import sha256
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from aifootball.service.halls.operations import lock_request
from aifootball.service.captains.models import CaptainCommand
from aifootball.service.errors import DomainError

def command(db,actor,request_id,kind,payload,execute):
    lock_request(db,request_id)
    digest=sha256(json.dumps(jsonable_encoder(payload),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    prior=db.scalar(select(CaptainCommand).where(CaptainCommand.request_id==request_id))
    if prior:
        if prior.actor_id!=actor or prior.kind!=kind or prior.request_hash!=digest:raise DomainError('idempotency_conflict','Ключ отправки уже использован',status=409)
        return prior.response
    result=jsonable_encoder(execute());db.add(CaptainCommand(actor_id=actor,request_id=request_id,kind=kind,request_hash=digest,response=result));return result
