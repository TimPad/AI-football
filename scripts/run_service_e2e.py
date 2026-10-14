"""Dedicated browser-test service. Never truncates or uses organizer data."""
from pathlib import Path
import os
os.chdir(Path(__file__).resolve().parents[1])
from sqlalchemy import create_engine, text, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from alembic.config import Config
from alembic import command
import uvicorn
from aifootball.service.config import Settings
from aifootball.service.app import create_app
from aifootball.service.auth.models import Admin
from aifootball.service.auth.cli import create_admin

base=Settings()
url=make_url(base.database_url).set(database='aifootball_e2e')
assert url.database=='aifootball_e2e'
engine=create_engine(base.database_url,isolation_level='AUTOCOMMIT')
with engine.connect() as db:
    if not db.scalar(text("SELECT 1 FROM pg_database WHERE datname='aifootball_e2e'")):
        db.execute(text('CREATE DATABASE aifootball_e2e'))
engine.dispose()
settings=Settings(database_url=url.render_as_string(hide_password=False),allowed_origin='http://127.0.0.1:8181',attachment_root=Path('data/service/e2e-attachments'))
cfg=Config('alembic.ini');cfg.attributes['database_url']=settings.database_url;command.upgrade(cfg,'head')
app=create_app(settings)
with Session(app.state.engine) as db:
    if not db.scalar(select(Admin).where(Admin.login=='e2e-admin')):
        create_admin(db,'e2e-admin','e2e-only-password')
    analyst=db.scalar(select(Admin).where(Admin.login=='e2e-analyst'))
    if not analyst:analyst=create_admin(db,'e2e-analyst','e2e-only-password')
    analyst.can_manage_analytics=True
    db.commit()
uvicorn.run(app,host='127.0.0.1',port=8181,log_level='warning')
