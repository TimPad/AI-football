from uuid import UUID
from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from aifootball.service.db import get_session
from aifootball.service.auth.security import require_analytics_admin,require_analytics_reader
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.ratings.schemas import ParticipationSave,ParticipationView,ParticipationOverview,ActionsSave,ActionsView,ActionsOverview
from aifootball.service.ratings.models import ParticipationVersion,ActionVersion
from aifootball.service.ratings.operations import save_participation,participation_overview,participation_view
from aifootball.service.ratings.actions import save_actions,action_view,action_overview

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


@router.get('/matches/{mid}/performance-actions',response_model=ActionsOverview,dependencies=[Depends(require_analytics_reader)])
def actions(mid:UUID,db:Session=Depends(get_session)):return action_overview(db,mid)


@router.get('/matches/{mid}/performance-actions/versions/{vid}',response_model=ActionsView,dependencies=[Depends(require_analytics_reader)])
def actions_version(mid:UUID,vid:UUID,db:Session=Depends(get_session)):
    value=get_entity(db,ActionVersion,vid)
    if value.match_id!=mid:raise DomainError('not_found','Версия действий не найдена',status=404)
    return action_view(value)


@router.put('/matches/{mid}/performance-actions',response_model=ActionsView)
def save_action_version(mid:UUID,data:ActionsSave,actor=Depends(require_analytics_admin),db:Session=Depends(get_session)):
    with db.begin():return save_actions(db,mid,actor.id,data)
