"""Run with python -m aifootball.service.catalog.roster_imports.cleanup."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from aifootball.service.config import Settings
from aifootball.service.db import make_engine, utcnow
from .models import RosterImport


def cleanup(db, now=None):
    expired = db.scalars(select(RosterImport).where(RosterImport.expires_at < (now or utcnow())).with_for_update()).all()
    for session in expired:
        if session.status == 'committed':
            session.source = {}; session.rows = []; session.configuration = {}; session.expected = {}
        else:
            db.delete(session)
    return len(expired)


if __name__ == '__main__':
    engine = make_engine(Settings().database_url)
    with Session(engine) as db, db.begin():
        count = cleanup(db)
    print(f'Expired previews cleaned: {count}')
