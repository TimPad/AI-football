def test_migration_ready_and_no_video_import(client):
    import sys
    r = client.get('/api/v1/ready')
    assert r.status_code == 200
    assert r.json()['schema_version']
    assert 'ultralytics' not in sys.modules


def test_clean_migration_upgrade_downgrade(service_settings):
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import create_engine, inspect
    # Использовать только ещё одну отдельную test БД, не уже наполненную fixture.
    from sqlalchemy.engine import make_url
    from sqlalchemy import text
    base = make_url(service_settings.database_url)
    engine = create_engine(base.render_as_string(hide_password=False), isolation_level='AUTOCOMMIT')
    with engine.connect() as db:
        if not db.scalar(text("SELECT 1 FROM pg_database WHERE datname='aifootball_migration_test'")):
            db.execute(text('CREATE DATABASE aifootball_migration_test'))
    url = base.set(database='aifootball_migration_test').render_as_string(hide_password=False)
    cfg = Config('alembic.ini'); cfg.attributes['database_url'] = url
    command.upgrade(cfg, 'head')
    command.downgrade(cfg, 'base')
    e = create_engine(url)
    assert 'admins' not in inspect(e).get_table_names()
    command.upgrade(cfg, 'head')
    assert 'admins' in inspect(e).get_table_names()
    e.dispose(); engine.dispose()
