from sqlalchemy import Column,String,Date,Integer,Boolean,Uuid,ForeignKey,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base,Entity


class Tournament(Entity,Base):
    __tablename__='tournaments'
    name=Column(String(200),nullable=False)
    season=Column(String(100),nullable=False)
    starts_on=Column(Date,nullable=False)
    ends_on=Column(Date,nullable=False)
    timezone=Column(String(100),nullable=False)
    revision=Column(Integer,nullable=False,default=0)
    archived=Column(Boolean,nullable=False,default=False)
    visibility=Column(String(10),nullable=False,default='draft',server_default='draft')


class RegulationVersion(Entity,Base):
    __tablename__='regulations'
    tournament_id=Column(Uuid,ForeignKey('tournaments.id',name='fk_regulation_tournament'),nullable=False)
    variant_name=Column(String(100),nullable=False)
    version=Column(Integer,nullable=False)
    rules=Column(JSONB,nullable=False)
    __table_args__=(UniqueConstraint('tournament_id','variant_name','version',name='uq_regulation_version'),)
