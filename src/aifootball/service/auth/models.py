from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, Uuid, Index, Integer
from aifootball.service.db import Base, Entity, utcnow


class Admin(Entity, Base):
    __tablename__ = 'admins'
    login = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, default=True)


class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    id = Column(Integer, primary_key=True)
    login = Column(String(100), nullable=False)
    ip = Column(String(200), nullable=False)
    failed_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (Index('ix_login_attempts_login_ip_time', 'login', 'ip', 'failed_at'),)


class AdminSession(Base):
    __tablename__ = 'sessions'
    token_hash = Column(String(64), primary_key=True)
    admin_id = Column(Uuid, ForeignKey('admins.id', name='fk_session_admin'), nullable=False)
    csrf_token = Column(String(100), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
