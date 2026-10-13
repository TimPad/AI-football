from pathlib import Path
from uuid import UUID,uuid5,NAMESPACE_URL
from urllib.parse import quote
from fastapi import APIRouter,Depends,File,UploadFile,Request,Header
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from aifootball.service.auth.security import require_admin,require_csrf
from aifootball.service.common import get_entity,as_dict
from aifootball.service.db import get_session
from aifootball.service.errors import DomainError
from aifootball.service.protocol.models import Attachment
from aifootball.service.protocol.schemas import Command
from aifootball.service.protocol.commands import record_command
from aifootball.service.matches.models import Match
from aifootball.service.storage.attachments import AttachmentStore

router=APIRouter()


@router.post('/matches/{mid}/attachments')
def upload(mid:UUID,request:Request,file:UploadFile=File(),request_id:UUID=Header(alias='X-Request-ID'),
           expected_revision:int=Header(alias='X-Expected-Revision',ge=0),db:Session=Depends(get_session),actor=Depends(require_csrf)):
    store=AttachmentStore(request.app.state.settings.attachment_root)
    # UUID зависит только от конкретного матча и команды; повтор не создаёт другой документ.
    aid=uuid5(NAMESPACE_URL,f'aifootball:attachment:{mid}:{request_id}')
    name=Path((file.filename or 'Протокол').replace('\\','/')).name[:240]
    info=None
    with db.begin():
        match=get_entity(db,Match,mid,lock=True)
        from aifootball.service.matches.models import MatchCommand
        from aifootball.service.errors import RevisionConflict
        prior=db.scalar(select(MatchCommand).where(MatchCommand.match_id==mid,MatchCommand.request_id==request_id))
        if prior is None and match.revision!=expected_revision: raise RevisionConflict(match.revision)
        try:
            info=store.put(aid,file.file,file.content_type)
            extension={'application/pdf':'.pdf','image/png':'.png','image/jpeg':'.jpg'}[info.mime]
            name=Path(name).stem+extension
            attachment=db.get(Attachment,aid)
            if attachment is None:
                attachment=Attachment(id=aid,match_id=mid,original_name=name,storage_key=info.key,
                    mime=info.mime,size=info.size,sha256=info.sha256,created_by=actor.id)
                db.add(attachment); db.flush()
            if attachment.sha256!=info.sha256 or attachment.original_name!=name:
                raise DomainError('idempotency_conflict','Ключ загрузки уже использован',status=409)
            command=Command(request_id=request_id,expected_revision=expected_revision,kind='add_attachment',
                payload={'attachment_id':str(aid)})
            return record_command(db,match,command,actor)
        except Exception:
            # Удаляем только созданный этим запросом файл, пока блокировка матча ещё удерживается.
            if info is not None and info.created: (store.root/info.key).unlink(missing_ok=True)
            raise


@router.get('/matches/{mid}/attachments',dependencies=[Depends(require_admin)])
def attachments(mid:UUID,db:Session=Depends(get_session)):
    match=get_entity(db,Match,mid)
    ids=[UUID(value) for value in match.protocol['attachment_ids']]
    rows=db.scalars(select(Attachment).where(Attachment.id.in_(ids))).all() if ids else []
    return {'items':[{k:v for k,v in as_dict(row).items() if k not in ['storage_key','sha256']} for row in rows],'total':len(rows)}


@router.get('/attachments/{aid}/download',dependencies=[Depends(require_admin)])
def download(aid:UUID,request:Request,db:Session=Depends(get_session)):
    row=get_entity(db,Attachment,aid)
    store=AttachmentStore(request.app.state.settings.attachment_root)
    try: stream=store.open(row.storage_key)
    except FileNotFoundError: raise DomainError('not_found','Файл документа недоступен',status=404)
    def chunks():
        with stream:
            while part:=stream.read(1024*1024): yield part
    return StreamingResponse(chunks(),media_type=row.mime,headers={
        'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row.original_name),
        'X-Content-Type-Options':'nosniff','Content-Length':str(row.size)})
