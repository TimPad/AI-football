def test_migration_ready_and_no_video_import(client):
    import sys

    r = client.get('/api/v1/ready')
    assert r.status_code == 200
    assert r.json()['schema_version']
    assert 'ultralytics' not in sys.modules


def test_clean_migration_upgrade_downgrade(service_settings):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text

    # Использовать только ещё одну отдельную test БД, не уже наполненную fixture.
    from sqlalchemy.engine import make_url

    base = make_url(service_settings.database_url)
    engine = create_engine(base.render_as_string(hide_password=False), isolation_level='AUTOCOMMIT')
    with engine.connect() as db:
        if not db.scalar(text("SELECT 1 FROM pg_database WHERE datname='aifootball_migration_test'")):
            db.execute(text('CREATE DATABASE aifootball_migration_test'))
    url = base.set(database='aifootball_migration_test').render_as_string(hide_password=False)
    cfg = Config('alembic.ini')
    cfg.attributes['database_url'] = url
    command.upgrade(cfg, 'head')
    command.downgrade(cfg, 'base')
    e = create_engine(url)
    assert 'admins' not in inspect(e).get_table_names()
    command.upgrade(cfg, 'head')
    assert 'admins' in inspect(e).get_table_names()
    e.dispose()
    engine.dispose()


def test_visibility_migration_preserves_existing_public_tournaments(service_settings):
    from uuid import uuid4

    from alembic import command
    from alembic.config import Config
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
        db.execute(
            text("""INSERT INTO tournaments
            (id, created_at, name, season, starts_on, ends_on, timezone, revision, archived)
            VALUES (:id, now(), 'Исторический турнир', '2026', '2026-10-01', '2026-12-31',
                    'Europe/Moscow', 0, false)"""),
            {'id': identifier},
        )
    command.upgrade(cfg, 'head')
    with engine.connect() as db:
        assert (
            db.execute(text('SELECT visibility FROM tournaments WHERE id=:id'), {'id': identifier}).scalar_one()
            == 'public'
        )
    engine.dispose()


def test_stage_tables_and_standings_flag(client):
    from sqlalchemy import inspect

    engine = client.app.state.engine
    names = inspect(engine).get_table_names()
    assert {'stages', 'stage_draws', 'fixtures', 'stage_withdrawals'} <= set(names)
    assert 'outcome' in {c['name'] for c in inspect(engine).get_columns('fixtures')}
    assert 'participants' in {c['name'] for c in inspect(engine).get_columns('stage_draws')}
    column = next(c for c in inspect(engine).get_columns('tournaments') if c['name'] == 'standings_public')
    assert not column['nullable'] and 'true' in str(column['default'])


def test_camera_motion_migration_keeps_fixed_profiles_and_guards_ptz(service_settings):
    """Прежние версии профиля становятся неподвижными с прежним контуром; откат при поворотных отказывает."""
    import json
    from uuid import uuid4

    import pytest
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(service_settings.database_url).set(database='aifootball_migration_test')
    assert url.database.endswith('_test')
    cfg = Config('alembic.ini')
    cfg.attributes['database_url'] = url.render_as_string(hide_password=False)
    command.upgrade(cfg, 'head')
    command.downgrade(cfg, '0028_stage_adjustments')
    hall, fixed, ptz = uuid4(), uuid4(), uuid4()
    columns = """id, created_at, hall_id, name, version, request_id, request_hash, hall_revision, pitch_length_m,
        pitch_width_m, frame_width, frame_height, points, pitch_polygon_px, homography, reprojection_error_m"""
    values = """:id, now(), :hall, :name, 1, :request, 'h', 1, 40, 20, 400, 200, '[]', CAST(:polygon AS jsonb),
        '[[0.1,0,0],[0,0.1,0],[0,0,1]]', 0.01"""
    polygon = json.dumps([[0, 0], [399, 0], [399, 199], [0, 199]])
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(
            text("""INSERT INTO halls (id, created_at, name, address, address_source, pitch_length_m,
                pitch_width_m, surface, description, archived, revision)
                VALUES (:id, now(), 'Зал', 'Адрес', 'manual', 40, 20, '', '', false, 1)"""),
            {'id': hall},
        )
        db.execute(
            text(f'INSERT INTO camera_profiles ({columns}) VALUES ({values})'),
            {'id': fixed, 'hall': hall, 'name': 'Старая', 'request': uuid4(), 'polygon': polygon},
        )
    command.upgrade(cfg, 'head')
    with engine.begin() as db:
        row = db.execute(
            text('SELECT motion, pitch_polygon_px, overlay FROM camera_profiles WHERE id=:id'), {'id': fixed}
        ).one()
        assert tuple(row) == ('fixed', json.loads(polygon), None)
        db.execute(
            text(f"INSERT INTO camera_profiles ({columns}, motion, overlay) VALUES ({values}, 'ptz', '[]')"),
            {'id': ptz, 'hall': hall, 'name': 'Трансляция', 'request': uuid4(), 'polygon': None},
        )
    with pytest.raises(RuntimeError, match='поворотной камеры'):
        command.downgrade(cfg, '0028_stage_adjustments')
    with engine.begin() as db:
        db.execute(text('DELETE FROM camera_profiles'))
        db.execute(text('DELETE FROM halls WHERE id=:id'), {'id': hall})
    command.upgrade(cfg, 'head')
    engine.dispose()
