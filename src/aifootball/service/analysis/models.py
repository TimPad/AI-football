from sqlalchemy import Column, Uuid, String, Integer, ForeignKey, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base, Entity


class AnalysisJob(Entity, Base):
    __tablename__ = 'analysis_jobs'
    match_id = Column(Uuid, ForeignKey('matches.id'), nullable=False)
    created_by = Column(Uuid, ForeignKey('admins.id'), nullable=False)
    context_hash = Column(String(64), nullable=False)
    context = Column(JSONB, nullable=False)
    cv_files = Column(JSONB, nullable=False)


class AnalysisRun(Entity, Base):
    __tablename__ = 'analysis_runs'
    job_id = Column(Uuid, ForeignKey('analysis_jobs.id'), nullable=False)
    match_id = Column(Uuid, ForeignKey('matches.id'), nullable=False)
    created_by = Column(Uuid, ForeignKey('admins.id'), nullable=False)
    source_run_id = Column(Uuid, ForeignKey('analysis_runs.id'))
    content_hash = Column(String(64), nullable=False)
    storage_key = Column(String(100), nullable=False)
    manifest = Column(JSONB, nullable=False)
    report = Column(JSONB, nullable=False)
    tracks = Column(JSONB, nullable=False)
    checks = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, default='review')
    revision = Column(Integer, nullable=False, default=0)
    side_map = Column(JSONB, nullable=False, default=lambda: {'A': 'home', 'B': 'away'})
    confirmed_by = Column(Uuid, ForeignKey('admins.id'))
    __table_args__ = (Index('uq_analysis_import_content', 'job_id', 'content_hash', unique=True,
                           postgresql_where=text('source_run_id IS NULL')),)


class AnalysisAssignment(Base):
    __tablename__ = 'analysis_assignments'
    run_id = Column(Uuid, ForeignKey('analysis_runs.id'), primary_key=True)
    track_id = Column(Integer, primary_key=True)
    player_id = Column(Uuid, ForeignKey('players.id'))
    excluded_reason = Column(String(500))


class PlayerMatchMetric(Base):
    __tablename__ = 'player_match_metrics'
    run_id = Column(Uuid, ForeignKey('analysis_runs.id'), primary_key=True)
    player_id = Column(Uuid, ForeignKey('players.id'), primary_key=True)
    match_id = Column(Uuid, ForeignKey('matches.id'), nullable=False, index=True)
    display_name = Column(String(200), nullable=False)
    shirt_number = Column(String(10))
    side = Column(String(10), nullable=False)
    track_ids = Column(JSONB, nullable=False)
    metrics = Column(JSONB, nullable=False)


class AnalysisCommand(Entity, Base):
    __tablename__ = 'analysis_commands'
    match_id = Column(Uuid, ForeignKey('matches.id'), nullable=False)
    actor_id = Column(Uuid, ForeignKey('admins.id'), nullable=False)
    request_id = Column(Uuid, nullable=False)
    request_hash = Column(String(64), nullable=False)
    response = Column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint('match_id', 'request_id', name='uq_analysis_command_request'),)
