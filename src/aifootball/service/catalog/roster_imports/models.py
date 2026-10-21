from sqlalchemy import Column, String, Uuid, Integer, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base, Entity


class RosterImport(Entity, Base):
    __tablename__ = 'roster_imports'
    actor_kind = Column(String(10), nullable=False, default='admin')
    actor_id = Column(Uuid, nullable=False)
    scope = Column(String(20), nullable=False)
    target_id = Column(Uuid, nullable=False)
    revision = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default='draft')
    expires_at = Column(DateTime(timezone=True), nullable=False)
    source = Column(JSONB, nullable=False)
    configuration = Column(JSONB, nullable=False, default=dict)
    rows = Column(JSONB, nullable=False, default=list)
    expected = Column(JSONB, nullable=False, default=dict)
    summary = Column(JSONB, nullable=False, default=dict)
    commit_request_id = Column(Uuid, nullable=True, unique=True)
    commit_revision = Column(Integer, nullable=True)
    result = Column(JSONB, nullable=True)
