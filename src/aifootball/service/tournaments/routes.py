from uuid import UUID
from pydantic import ValidationError
from fastapi import APIRouter,Depends,Query
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from aifootball.service.auth.security import require_admin,require_csrf
from aifootball.service.common import as_dict,get_entity,list_entities
from aifootball.service.db import get_session
from aifootball.service.errors import DomainError,RevisionConflict
from aifootball.service.tournaments.models import Tournament,RegulationVersion
from aifootball.service.tournaments.schemas import Regulation,TournamentCreate,TournamentPatch,RegulationCreate

from aifootball.service.views import Page,TournamentView,RegulationView,Preset

router=APIRouter(prefix='/tournaments')


@router.get('/regulation-presets',response_model=Page[Preset],dependencies=[Depends(require_admin)])
def presets():
    return {'items':[{'name':'Футзал — стартовый шаблон','rules':Regulation().model_dump()}],'total':1}


@router.get('',response_model=Page[TournamentView],dependencies=[Depends(require_admin)])
def listing(db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    return list_entities(db,Tournament,limit=limit,offset=offset)


@router.post('',response_model=TournamentView,status_code=201,dependencies=[Depends(require_csrf)])
def create(data:TournamentCreate,db:Session=Depends(get_session)):
    row=Tournament(**data.model_dump()); db.add(row); db.commit(); return as_dict(row)


@router.get('/{tid}',response_model=TournamentView,dependencies=[Depends(require_admin)])
def detail(tid:UUID,db:Session=Depends(get_session)):
    return as_dict(get_entity(db,Tournament,tid))


@router.patch('/{tid}',response_model=TournamentView,dependencies=[Depends(require_csrf)])
def update(tid:UUID,data:TournamentPatch,db:Session=Depends(get_session)):
    with db.begin():
        row=get_entity(db,Tournament,tid,lock=True)
        if row.revision!=data.expected_revision: raise RevisionConflict(row.revision)
        values=data.model_dump(exclude_unset=True,exclude={'expected_revision'})
        if any(value is None for value in values.values()):
            raise DomainError('validation','Не очищайте обязательные поля')
        current={key:getattr(row,key) for key in TournamentCreate.model_fields}
        try:
            TournamentCreate.model_validate({**current,**{k:v for k,v in values.items() if k!='archived'}})
        except ValidationError as error:
            raise DomainError('validation','Проверьте настройки турнира',
                {'.'.join(map(str,e['loc'])):e['msg'] for e in error.errors()}) from error
        for key,value in values.items(): setattr(row,key,value)
        row.revision+=1
    return as_dict(row)


@router.get('/{tid}/regulations',response_model=Page[RegulationView],dependencies=[Depends(require_admin)])
def regulations(tid:UUID,db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    get_entity(db,Tournament,tid)
    return list_entities(db,RegulationVersion,where=[RegulationVersion.tournament_id==tid],
                         limit=limit,offset=offset,order=RegulationVersion.version.desc())


@router.post('/{tid}/regulations',response_model=RegulationView,status_code=201,dependencies=[Depends(require_csrf)])
def new_regulation(tid:UUID,data:RegulationCreate,db:Session=Depends(get_session)):
    with db.begin():
        tournament=get_entity(db,Tournament,tid,lock=True)
        if tournament.archived: raise DomainError('archived','Турнир в архиве')
        version=db.scalar(select(func.max(RegulationVersion.version)).where(
            RegulationVersion.tournament_id==tid,RegulationVersion.variant_name==data.variant_name)) or 0
        row=RegulationVersion(tournament_id=tid,variant_name=data.variant_name,version=version+1,rules=data.rules.model_dump())
        db.add(row)
    return as_dict(row)
