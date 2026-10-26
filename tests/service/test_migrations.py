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


def test_visibility_migration_preserves_existing_public_tournaments(service_settings):
    from uuid import uuid4
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(service_settings.database_url).set(database='aifootball_migration_test')
    assert url.database.endswith('_test')
    cfg = Config('alembic.ini')
    cfg.attributes['database_url'] = url.render_as_string(hide_password=False)
    command.upgrade(cfg, 'head')
    command.downgrade(cfg, '0015_camera_reference')
    identifier = uuid4()
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("""INSERT INTO tournaments
            (id, created_at, name, season, starts_on, ends_on, timezone, revision, archived)
            VALUES (:id, now(), 'Исторический турнир', '2026', '2026-10-01', '2026-12-31',
                    'Europe/Moscow', 0, false)"""), {'id': identifier})
    command.upgrade(cfg, 'head')
    with engine.connect() as db:
        assert db.execute(text('SELECT visibility FROM tournaments WHERE id=:id'), {'id': identifier}).scalar_one() == 'public'
    engine.dispose()


def test_stage_tables_and_standings_flag(client):
    from sqlalchemy import inspect
    engine = client.app.state.engine
    names = inspect(engine).get_table_names()
    assert {'stages', 'stage_draws', 'fixtures'} <= set(names)
    column = next(c for c in inspect(engine).get_columns('tournaments') if c['name'] == 'standings_public')
    assert not column['nullable'] and 'true' in str(column['default'])
