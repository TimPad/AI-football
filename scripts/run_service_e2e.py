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
database=os.environ.get('AIF_E2E_DATABASE_NAME','aifootball_e2e')
assert database.startswith('aifootball_') and database.endswith('_e2e') and database.replace('_','').isalnum()
port=int(os.environ.get('AIF_E2E_PORT','8181'))
url=make_url(base.database_url).set(database=database)
engine=create_engine(base.database_url,isolation_level='AUTOCOMMIT')
with engine.connect() as db:
    if not db.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"),{'name':database}):
        db.execute(text(f'CREATE DATABASE {database}'))
engine.dispose()
settings=Settings(database_url=url.render_as_string(hide_password=False),allowed_origin=f'http://127.0.0.1:{port}',attachment_root=Path(f'data/service/{database}-attachments'))
cfg=Config('alembic.ini');cfg.attributes['database_url']=settings.database_url;command.upgrade(cfg,'head')
# AIF_WEB_DIST — отдельная сборка интерфейса ветки: общая web/dist остаётся у сервиса организатора.
app=create_app(settings,web_dist=os.environ.get('AIF_WEB_DIST') or None)
with Session(app.state.engine) as db:
    if not db.scalar(select(Admin).where(Admin.login=='e2e-admin')):
        create_admin(db,'e2e-admin','e2e-only-password')
    analyst=db.scalar(select(Admin).where(Admin.login=='e2e-analyst'))
    if not analyst:analyst=create_admin(db,'e2e-analyst','e2e-only-password')
    analyst.can_manage_analytics=True
    db.commit()
uvicorn.run(app,host='127.0.0.1',port=port,log_level='warning')
