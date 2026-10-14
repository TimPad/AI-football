from sqlalchemy import Column,Uuid,Integer,String,ForeignKey,UniqueConstraint,CheckConstraint,Index
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base,Entity


class ParticipationVersion(Entity,Base):
    __tablename__='participation_versions'
    match_id=Column(Uuid,ForeignKey('matches.id'),nullable=False)
    revision=Column(Integer,nullable=False)
    status=Column(String(20),nullable=False)
    created_by=Column(Uuid,ForeignKey('admins.id'),nullable=False)
    source_analysis_run_id=Column(Uuid,ForeignKey('analysis_runs.id'))
    source_protocol_version_id=Column(Uuid,ForeignKey('protocol_versions.id'))
    context_hash=Column(String(64),nullable=False)
    document=Column(JSONB,nullable=False)
    provenance=Column(JSONB,nullable=False)
    lineup=Column(JSONB,nullable=False)
    __table_args__=(UniqueConstraint('match_id','revision',name='uq_participation_match_revision'),
        CheckConstraint("status IN ('review','confirmed') AND revision>0",name='ck_participation_status_revision'),
        Index('ix_participation_match_status','match_id','status','revision'))


class ActionVersion(Entity,Base):
    __tablename__='performance_action_versions'
    match_id=Column(Uuid,ForeignKey('matches.id'),nullable=False)
    revision=Column(Integer,nullable=False)
    status=Column(String(20),nullable=False)
    created_by=Column(Uuid,ForeignKey('admins.id'),nullable=False)
    source_participation_version_id=Column(Uuid,ForeignKey('participation_versions.id'))
    source_analysis_run_id=Column(Uuid,ForeignKey('analysis_runs.id'))
    source_protocol_version_id=Column(Uuid,ForeignKey('protocol_versions.id'))
    context_hash=Column(String(64),nullable=False)
    document=Column(JSONB,nullable=False)
    provenance=Column(JSONB,nullable=False)
    lineup=Column(JSONB,nullable=False)
    canonical_actions=Column(JSONB,nullable=False)
    __table_args__=(UniqueConstraint('match_id','revision',name='uq_action_match_revision'),
        CheckConstraint("status IN ('review','confirmed') AND revision>0",name='ck_action_status_revision'),
        Index('ix_action_match_status','match_id','status','revision'))
