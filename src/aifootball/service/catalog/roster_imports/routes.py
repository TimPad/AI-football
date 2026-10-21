from datetime import timedelta
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, Form, Response
from sqlalchemy.orm import Session
from aifootball.service.auth.security import require_admin, require_csrf
from aifootball.service.db import get_session, utcnow
from .models import RosterImport
from .schemas import ImportView, ImportPreviewInput, ImportCommit, ImportResult
from .preview import target_entity, owned_import, import_view, build_preview
from .operations import apply_import
from .xlsx import read_workbook, template, report_workbook, FILE_LIMIT

router = APIRouter(prefix='/roster-imports')
XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


@router.get('/template', dependencies=[Depends(require_admin)])
def download_template(scope: Literal['team', 'tournament'] = 'tournament'):
    return Response(template(scope), media_type=XLSX_TYPE, headers={
        'Content-Disposition': 'attachment; filename="roster-template.xlsx"', 'Cache-Control': 'private, no-store'})


@router.post('', response_model=ImportView, status_code=201)
def upload(scope: Literal['team', 'tournament'] = Form(), target_id: UUID = Form(),
           file: UploadFile = File(), entry_id: UUID | None = Form(default=None),
           admin=Depends(require_csrf), db: Session = Depends(get_session)):
    source = read_workbook(file.file.read(FILE_LIMIT + 1), file.filename or '')
    with db.begin():
        target_entity(db, scope, target_id)
        if entry_id is not None:
            from aifootball.service.catalog.models import Entry
            from aifootball.service.common import get_entity
            from aifootball.service.errors import DomainError
            entry=get_entity(db,Entry,entry_id)
            if scope!='tournament' or entry.tournament_id!=target_id:
                raise DomainError('import_entry','Заявка относится к другому турниру',status=404)
            source['entry_id']=str(entry_id)
        session = RosterImport(actor_kind='admin', actor_id=admin.id, scope=scope, target_id=target_id,
                              expires_at=utcnow() + timedelta(days=7), source=source)
        db.add(session); db.flush()
        return import_view(session)


@router.get('/{identifier}', response_model=ImportView)
def detail(identifier: UUID, admin=Depends(require_admin), db: Session = Depends(get_session)):
    return import_view(owned_import(db, identifier, admin.id))


@router.put('/{identifier}/preview', response_model=ImportView)
def preview(identifier: UUID, data: ImportPreviewInput, admin=Depends(require_csrf), db: Session = Depends(get_session)):
    with db.begin():
        return build_preview(db, owned_import(db, identifier, admin.id, lock=True), data)


@router.post('/{identifier}/commit', response_model=ImportResult)
def commit(identifier: UUID, data: ImportCommit, admin=Depends(require_csrf), db: Session = Depends(get_session)):
    with db.begin():
        return apply_import(db, identifier, admin.id, data)


@router.get('/{identifier}/report')
def download_report(identifier: UUID, admin=Depends(require_admin), db: Session = Depends(get_session)):
    session = owned_import(db, identifier, admin.id)
    return Response(report_workbook(session.rows), media_type=XLSX_TYPE, headers={
        'Content-Disposition': 'attachment; filename="roster-review.xlsx"', 'Cache-Control': 'private, no-store'})


@router.delete('/{identifier}', status_code=204)
def cancel(identifier: UUID, admin=Depends(require_csrf), db: Session = Depends(get_session)):
    from aifootball.service.errors import DomainError
    with db.begin():
        session = owned_import(db, identifier, admin.id, lock=True)
        if session.status == 'committed':
            raise DomainError('already_committed', 'Применённый импорт остаётся в истории', status=409)
        db.delete(session)
