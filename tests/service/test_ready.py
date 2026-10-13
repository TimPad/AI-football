from fastapi.testclient import TestClient
from aifootball.service.app import create_app
from aifootball.service.config import Settings

def test_readiness_rejects_outdated_migration(client):
    from sqlalchemy import text
    with client.app.state.engine.begin() as db:
        original=db.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        db.execute(text("UPDATE alembic_version SET version_num='0001_auth'"))
    try:
        assert client.get('/api/v1/ready').status_code==503
    finally:
        with client.app.state.engine.begin() as db:
            db.execute(text('UPDATE alembic_version SET version_num=:v'),{'v':original})

def test_readiness_without_database_is_503():
    settings=Settings(database_url='postgresql+psycopg://test:test@127.0.0.1:1/missing?connect_timeout=1')
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/v1/ready').status_code==503
