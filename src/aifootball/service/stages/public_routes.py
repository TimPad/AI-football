"""Таблицы, сетка и пары без даты для зрителя — только по опубликованным протоколам."""
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from aifootball.service.db import get_session
from aifootball.service.public_visibility import require_public_tournament
from aifootball.service.views import Page
from aifootball.service.stages import operations as ops
from aifootball.service.stages.schemas import StandingsView, FixtureView

router = APIRouter(prefix='/public')


@router.get('/tournaments/{tid}/standings', response_model=StandingsView)
def standings(tid: UUID, db: Session = Depends(get_session)):
    return ops.standings(db, require_public_tournament(db, tid), 'public')


@router.get('/tournaments/{tid}/fixtures', response_model=Page[FixtureView])
def fixtures(tid: UUID, db: Session = Depends(get_session)):
    return ops.fixture_list(db, require_public_tournament(db, tid), 'public', unscheduled=True)
