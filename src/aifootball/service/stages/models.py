"""Этапы турнира, подтверждённые версии жеребьёвки и пары этапа."""
from sqlalchemy import Column,String,Integer,Boolean,Uuid,ForeignKey,DateTime,UniqueConstraint,CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base,Entity,utcnow


class Stage(Entity,Base):
    __tablename__='stages'
    tournament_id=Column(Uuid,ForeignKey('tournaments.id',name='fk_stage_tournament'),nullable=False,index=True)
    position=Column(Integer,nullable=False)
    name=Column(String(100),nullable=False)
    kind=Column(String(20),nullable=False)
    regulation_id=Column(Uuid,ForeignKey('regulations.id',name='fk_stage_regulation'),nullable=False)
    config=Column(JSONB,nullable=False)
    lots=Column(JSONB,nullable=False,default=dict,server_default='{}')
    revision=Column(Integer,nullable=False,default=0)
    __table_args__=(UniqueConstraint('tournament_id','position',name='uq_stage_position'),
        CheckConstraint("kind in ('round_robin','groups','single_elim','double_elim','swiss')",name='ck_stage_kind'))


class StageDraw(Entity,Base):
    __tablename__='stage_draws'
    stage_id=Column(Uuid,ForeignKey('stages.id',name='fk_draw_stage'),nullable=False)
    version=Column(Integer,nullable=False)
    method=Column(String(20),nullable=False)
    seed=Column(Integer,nullable=False)
    seeding=Column(JSONB,nullable=False)
    placement=Column(JSONB,nullable=False)
    confirmed_by=Column(Uuid,ForeignKey('admins.id',name='fk_draw_admin'),nullable=False)
    confirmed_at=Column(DateTime(timezone=True),nullable=False,default=utcnow)
    __table_args__=(UniqueConstraint('stage_id','version',name='uq_stage_draw_version'),)


class Fixture(Entity,Base):
    __tablename__='fixtures'
    stage_id=Column(Uuid,ForeignKey('stages.id',name='fk_fixture_stage'),nullable=False,index=True)
    draw_id=Column(Uuid,ForeignKey('stage_draws.id',name='fk_fixture_draw'),nullable=False)
    key=Column(String(20),nullable=False)
    leg=Column(Integer,nullable=False,default=1)
    group_no=Column(Integer)
    round_no=Column(Integer,nullable=False)
    bracket=Column(String(20))
    slot=Column(Integer,nullable=False,default=0)
    home_entry_id=Column(Uuid,ForeignKey('entries.id',name='fk_fixture_home'))
    away_entry_id=Column(Uuid,ForeignKey('entries.id',name='fk_fixture_away'))
    home_source=Column(JSONB)
    away_source=Column(JSONB)
    bye=Column(Boolean,nullable=False,default=False)
    match_id=Column(Uuid,ForeignKey('matches.id',name='fk_fixture_match'),unique=True)
    __table_args__=(UniqueConstraint('draw_id','key','leg',name='uq_fixture_key'),
        CheckConstraint('home_entry_id is null or away_entry_id is null or home_entry_id != away_entry_id',name='ck_fixture_teams'))
