from io import BytesIO
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import select
from fastapi.encoders import jsonable_encoder
from aifootball.service.analysis.context import build_context, canonical_json, context_hash
from aifootball.service.analysis.models import AnalysisJob, AnalysisCommand
from aifootball.service.analysis.schemas import JobView
from aifootball.service.halls.operations import lock_request
from aifootball.service.errors import DomainError


def command_hash(match_id, kind, payload):
    return context_hash({'match_id': str(match_id), 'kind': kind, 'payload': payload})


def prior_command(db, match_id, actor_id, request_id, kind, payload):
    lock_request(db, request_id)
    hashed = command_hash(match_id, kind, payload)
    prior = db.scalar(select(AnalysisCommand).where(AnalysisCommand.match_id == match_id,
                                                   AnalysisCommand.request_id == request_id))
    if prior and (prior.request_hash != hashed or prior.actor_id != actor_id):
        raise DomainError('idempotency_conflict', 'Ключ команды уже использован', status=409)
    return prior, hashed


def remember(db, match_id, actor_id, request_id, hashed, response):
    response = jsonable_encoder(response)
    db.add(AnalysisCommand(match_id=match_id, actor_id=actor_id, request_id=request_id,
                           request_hash=hashed, response=response))
    return response


def create_job(db, match_id, actor_id, request_id):
    prior, hashed = prior_command(db, match_id, actor_id, request_id, 'job', {})
    if prior:
        return prior.response
    context = build_context(db, match_id)
    from aifootball.service.halls.routes import export_cv
    with ZipFile(BytesIO(export_cv(match_id, db).body)) as archive:
        files = {name: archive.read(name).decode() for name in archive.namelist()}
    job = AnalysisJob(id=uuid5(NAMESPACE_URL, f'aifootball:job:{match_id}:{request_id}'),
                      match_id=match_id, created_by=actor_id, context=context,
                      context_hash=context_hash(context), cv_files=files)
    db.add(job); db.flush()
    view = JobView(id=job.id, match_id=job.match_id, created_at=job.created_at,
                   context_hash=job.context_hash, context=job.context)
    return remember(db, match_id, actor_id, request_id, hashed, view.model_dump(mode='json'))


def export_job(job, attachment_root):
    from hashlib import sha256
    from aifootball.service.halls.frames import reference_path
    contract = {'contract_version': '1', 'job_id': str(job.id), 'match_id': str(job.match_id),
                'context_hash': job.context_hash, 'context': job.context}
    files = {name: value.encode() for name, value in {**job.cv_files, 'job.json': canonical_json(contract).decode()}.items()}
    camera = job.context['camera']
    if camera.get('reference_sha256'):
        path = reference_path(attachment_root, camera['id'])
        raw = path.read_bytes() if path.is_file() else b''
        if sha256(raw).hexdigest() != camera['reference_sha256']:
            raise DomainError('reference_missing', 'Эталонный кадр камеры недоступен в хранилище', status=409)
        files['reference.jpg'] = raw
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as archive:
        for name, value in sorted(files.items()):
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)); info.compress_type = ZIP_DEFLATED
            archive.writestr(info, value)
    return buffer.getvalue()
