from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, DateTime, Uuid, create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from fastapi import Request


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Entity:
    id = Column(Uuid, primary_key=True, default=uuid4)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


def make_engine(url):
    return create_engine(url, pool_pre_ping=True)


def get_session(request: Request):
    with Session(request.app.state.engine) as session:
        yield session
