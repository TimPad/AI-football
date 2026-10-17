from datetime import timedelta
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,UploadFile,File,Form,Response
from sqlalchemy.orm import Session
from aifootball.service.db import get_session,utcnow
from aifootball.service.errors import DomainError
from aifootball.service.captains.security import require_captain,require_captain_csrf,require_captain_team
from aifootball.service.catalog.roster_imports.models import RosterImport
from aifootball.service.catalog.roster_imports.schemas import ImportView,ImportPreviewInput,ImportCommit,ImportResult
from aifootball.service.catalog.roster_imports.preview import target_entity,owned_import,import_view,build_preview
from aifootball.service.catalog.roster_imports.operations import apply_import
from aifootball.service.catalog.roster_imports.xlsx import FILE_LIMIT,read_workbook,template,report_workbook
from aifootball.service.catalog.roster_imports.routes import XLSX_TYPE

router=APIRouter(prefix='/captain/roster-imports')
@router.get('/template',dependencies=[Depends(require_captain)])
def download_template(scope:Literal['team']='team'):
    return Response(template('team'),media_type=XLSX_TYPE,headers={'Content-Disposition':'attachment; filename="team-roster.xlsx"','Cache-Control':'no-store'})

@router.post('',response_model=ImportView,status_code=201)
def upload(scope:Literal['team']=Form(),target_id:UUID=Form(),file:UploadFile=File(),account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    with db.begin():
        require_captain_team(db,account,target_id);target_entity(db,'team',target_id)
        source=read_workbook(file.file.read(FILE_LIMIT+1),file.filename or '')
        row=RosterImport(actor_kind='captain',actor_id=account.id,scope='team',target_id=target_id,expires_at=utcnow()+timedelta(days=7),source=source);db.add(row);db.flush();return import_view(row)

@router.get('/{identifier}',response_model=ImportView)
def detail(identifier:UUID,account=Depends(require_captain),db:Session=Depends(get_session)):
    return import_view(owned_import(db,identifier,account.id,'captain'))

@router.put('/{identifier}/preview',response_model=ImportView)
def preview(identifier:UUID,data:ImportPreviewInput,account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    with db.begin():return build_preview(db,owned_import(db,identifier,account.id,'captain',lock=True),data)

@router.post('/{identifier}/commit',response_model=ImportResult)
def commit(identifier:UUID,data:ImportCommit,account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    with db.begin():return apply_import(db,identifier,account.id,data,'captain')

@router.get('/{identifier}/report')
def report(identifier:UUID,account=Depends(require_captain),db:Session=Depends(get_session)):
    row=owned_import(db,identifier,account.id,'captain')
    return Response(report_workbook(row.rows),media_type=XLSX_TYPE,headers={'Content-Disposition':'attachment; filename="roster-review.xlsx"','Cache-Control':'no-store'})

@router.delete('/{identifier}',status_code=204)
def cancel(identifier:UUID,account=Depends(require_captain_csrf),db:Session=Depends(get_session)):
    with db.begin():
        row=owned_import(db,identifier,account.id,'captain',lock=True)
        if row.status=='committed':raise DomainError('already_committed','Импорт уже применён',status=409)
        db.delete(row)
