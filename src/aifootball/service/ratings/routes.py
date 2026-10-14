from uuid import UUID
from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from aifootball.service.db import get_session
from aifootball.service.auth.security import require_analytics_admin,require_analytics_reader
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.ratings.schemas import ParticipationSave,ParticipationView,ParticipationOverview
from aifootball.service.ratings.models import ParticipationVersion
from aifootball.service.ratings.operations import save_participation,participation_overview,participation_view

router=APIRouter()


@router.get('/matches/{mid}/participation',response_model=ParticipationOverview,dependencies=[Depends(require_analytics_reader)])
def participation(mid:UUID,db:Session=Depends(get_session)):return participation_overview(db,mid)


@router.get('/matches/{mid}/participation/versions/{vid}',response_model=ParticipationView,dependencies=[Depends(require_analytics_reader)])
def version(mid:UUID,vid:UUID,db:Session=Depends(get_session)):
    value=get_entity(db,ParticipationVersion,vid)
    if value.match_id!=mid:raise DomainError('not_found','Версия участия не найдена',status=404)
    return participation_view(value)


@router.put('/matches/{mid}/participation',response_model=ParticipationView)
def save(mid:UUID,data:ParticipationSave,actor=Depends(require_analytics_admin),db:Session=Depends(get_session)):
    with db.begin():return save_participation(db,mid,actor.id,data)
