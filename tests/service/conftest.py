from pathlib import Path
import pytest
pytest.importorskip('fastapi')
pytest.importorskip('sqlalchemy')
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from aifootball.service.config import Settings
from aifootball.service.app import create_app
from aifootball.service.auth.cli import create_admin


@pytest.fixture(scope='session')
def service_settings(tmp_path_factory):
    base = Settings()
    url = make_url(base.database_url).set(database='aifootball_test')
    assert url.database.endswith('_test')
    engine = create_engine(base.database_url, isolation_level='AUTOCOMMIT')
    with engine.connect() as db:
        if not db.scalar(text("SELECT 1 FROM pg_database WHERE datname='aifootball_test'")):
            db.execute(text('CREATE DATABASE aifootball_test'))
    settings = Settings(database_url=url.render_as_string(hide_password=False),
                        attachment_root=tmp_path_factory.mktemp('attachments'))
    cfg = Config('alembic.ini')
    cfg.attributes['database_url'] = settings.database_url
    command.upgrade(cfg, 'head')
    return settings


@pytest.fixture
def client(service_settings):
    app = create_app(service_settings)
    with app.state.engine.begin() as db:
        tables = db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename!='alembic_version'")).scalars().all()
        # Изолированная тестовая БД; перечень таблиц берём из нашего metadata в каждом этапе.
        if tables:
            from aifootball.service.db import Base
            known = set(Base.metadata.tables)
            names = [f'"{t}"' for t in tables if t in known]
            if names:
                db.execute(text('TRUNCATE ' + ','.join(names) + ' RESTART IDENTITY CASCADE'))
    with TestClient(app) as c:
        c.headers['Origin'] = service_settings.allowed_origin
        yield c
    app.state.engine.dispose()


@pytest.fixture
def seed_admin(client):
    with Session(client.app.state.engine) as db:
        admin = create_admin(db, 'admin', 'testing-admin-password')
        return {'id': str(admin.id), 'password': 'testing-admin-password'}


@pytest.fixture
def admin_client(client, seed_admin):
    r = client.post('/api/v1/auth/login', json={'login': 'admin', 'password': seed_admin['password']})
    assert r.status_code == 200
    client.headers['X-CSRF-Token'] = r.json()['csrf_token']
    return client


@pytest.fixture
def regulation_data():
    return {'periods_s': [1200,1200], 'clock_mode':'clean', 'clock_display':'remaining',
        'mixed_stop_last_s':None, 'break_s':[600], 'schedule_slot_s':5400,
        'timeouts':{'allowed':True,'duration_s':60,'count':1,'scope':'period'},
        'extra':{'enabled':False,'periods_s':[300,300],'clock_mode':'clean','mixed_stop_last_s':None},
        'shootout':{'enabled':False,'initial_attempts':5},'players_on_pitch':5,
        'tournament_roster_limit':30,'match_roster_limit':14,'pitch_length_m':40,'pitch_width_m':20,
        'fouls':{'enabled':True,'warning_threshold':5,'reset':'period','extra_carry':True},
        'points':{'win':3,'draw':1,'loss':0},'allow_draw':True}


@pytest.fixture
def tournament_factory(admin_client):
    def create(**changes):
        data={'name':'Тестовый кубок','season':'2026','starts_on':'2026-10-01',
              'ends_on':'2026-12-31','timezone':'Europe/Moscow', **changes}
        r=admin_client.post('/api/v1/tournaments', json=data)
        assert r.status_code==201, r.text
        return r.json()
    return create
