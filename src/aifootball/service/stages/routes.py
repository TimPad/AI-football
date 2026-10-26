from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from aifootball.service.auth.security import require_admin, require_csrf
from aifootball.service.common import get_entity
from aifootball.service.db import get_session
from aifootball.service.tournaments.models import Tournament
from aifootball.service.tournaments.commands import setup_command
from aifootball.service.views import MatchView, Page
from aifootball.service.stages import operations as ops
from aifootball.service.stages.models import Stage, Fixture
from aifootball.service.stages.schemas import (FormatCreate, StagePatch, DrawInput, DrawConfirm, LotInput, NextRound,
    FixtureSchedule, FixtureReplace, StandingsView, DrawPreview, FixtureView)

router = APIRouter()


def stage_scope(db, sid, lock=False):
    stage = get_entity(db, Stage, sid, lock=lock)
    return get_entity(db, Tournament, stage.tournament_id, lock=lock), stage


@router.get('/tournaments/{tid}/stages', response_model=StandingsView, dependencies=[Depends(require_admin)])
def stages(tid: UUID, db: Session = Depends(get_session)):
    return ops.standings(db, get_entity(db, Tournament, tid), 'cabinet', implicit=False)


@router.get('/tournaments/{tid}/standings', response_model=StandingsView, dependencies=[Depends(require_admin)])
def cabinet_standings(tid: UUID, db: Session = Depends(get_session)):
    return ops.standings(db, get_entity(db, Tournament, tid), 'cabinet')


@router.post('/tournaments/{tid}/format', response_model=StandingsView)
def create_format(tid: UUID, data: FormatCreate, admin=Depends(require_csrf), db: Session = Depends(get_session)):
    with db.begin():
        tournament = get_entity(db, Tournament, tid, lock=True)
        return setup_command(db, admin.id, data.request_id, 'stage-format', {'tournament_id': tid, **data.model_dump(mode='json')},
                             lambda: ops.create_format(db, tournament, data))


@router.patch('/stages/{sid}', response_model=StandingsView, dependencies=[Depends(require_csrf)])
def patch_stage(sid: UUID, data: StagePatch, db: Session = Depends(get_session)):
    with db.begin():
        tournament, stage = stage_scope(db, sid, lock=True)
        return ops.patch_stage(db, tournament, stage, data)


@router.post('/stages/{sid}/draw/preview', response_model=DrawPreview, dependencies=[Depends(require_csrf)])
def preview(sid: UUID, data: DrawInput, db: Session = Depends(get_session)):
    tournament, stage = stage_scope(db, sid)
    return ops.preview_draw(db, tournament, stage, data)


@router.post('/stages/{sid}/draw', response_model=StandingsView)
def confirm(sid: UUID, data: DrawConfirm, admin=Depends(require_csrf), db: Session = Depends(get_session)):
    with db.begin():
        tournament, stage = stage_scope(db, sid)
        return setup_command(db, admin.id, data.request_id, 'stage-draw', {'stage_id': sid, **data.model_dump(mode='json')},
                             lambda: ops.confirm_draw(db, admin, tournament, stage, data))


@router.post('/stages/{sid}/lots', response_model=StandingsView)
def lots(sid: UUID, data: LotInput, admin=Depends(require_csrf), db: Session = Depends(get_session)):
    with db.begin():
        tournament, stage = stage_scope(db, sid, lock=True)
        return setup_command(db, admin.id, data.request_id, 'stage-lot', {'stage_id': sid, **data.model_dump(mode='json')},
                             lambda: ops.set_lot(db, tournament, stage, data))


@router.post('/stages/{sid}/next-round', response_model=StandingsView)
def next_round(sid: UUID, data: NextRound, admin=Depends(require_csrf), db: Session = Depends(get_session)):
    with db.begin():
        tournament, stage = stage_scope(db, sid)
        return setup_command(db, admin.id, data.request_id, 'stage-next-round', {'stage_id': sid, **data.model_dump(mode='json')},
                             lambda: ops.next_swiss_round(db, admin, tournament, stage, data))


@router.get('/tournaments/{tid}/fixtures', response_model=Page[FixtureView], dependencies=[Depends(require_admin)])
def fixtures(tid: UUID, unscheduled: bool = False, db: Session = Depends(get_session)):
    return ops.fixture_list(db, get_entity(db, Tournament, tid), 'cabinet', unscheduled)


def fixture_tournament(db, fid):
    return get_entity(db, Tournament, get_entity(db, Stage, get_entity(db, Fixture, fid).stage_id).tournament_id)


@router.post('/fixtures/{fid}/schedule', response_model=MatchView, status_code=201)
def schedule(fid: UUID, data: FixtureSchedule, admin=Depends(require_csrf), db: Session = Depends(get_session)):
    with db.begin():
        tournament = fixture_tournament(db, fid)
        return setup_command(db, admin.id, data.request_id, 'fixture-schedule', {'fixture_id': fid, **data.model_dump(mode='json')},
                             lambda: ops.schedule_fixture(db, admin, tournament, fid, data))


@router.post('/fixtures/{fid}/replace')
def replace(fid: UUID, data: FixtureReplace, admin=Depends(require_csrf), db: Session = Depends(get_session)):
    with db.begin():
        tournament = fixture_tournament(db, fid)
        return setup_command(db, admin.id, data.request_id, 'fixture-replace', {'fixture_id': fid, **data.model_dump(mode='json')},
                             lambda: ops.replace_team(db, tournament, fid, data))
