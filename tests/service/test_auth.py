def test_private_session_contract():
    from aifootball.service.app import create_app
    from aifootball.service.config import Settings
    from fastapi.testclient import TestClient
    app = create_app(Settings(database_url='postgresql+psycopg://localhost/aifootball_test'))
    with TestClient(app) as client:
        assert client.get('/api/v1/health').status_code == 200
        assert client.get('/api/v1/auth/me').status_code == 401


def test_login_csrf_logout(client, seed_admin):
    assert client.get('/api/v1/auth/me').status_code == 401
    assert client.post('/api/v1/auth/login', json={'login': 'admin', 'password': 'wrong'}).status_code == 401
    r = client.post('/api/v1/auth/login', json={'login': 'admin', 'password': seed_admin['password']})
    assert r.status_code == 200
    assert 'HttpOnly' in r.headers['set-cookie']
    assert 'password_hash' not in r.json()
    assert client.get('/api/v1/auth/me').json()['login'] == 'admin'
    assert client.post('/api/v1/auth/logout').status_code == 403
    client.headers['X-CSRF-Token'] = r.json()['csrf_token']
    assert client.post('/api/v1/auth/logout').status_code == 204
    assert client.get('/api/v1/auth/me').status_code == 401


def test_origin_throttle_and_expired_session(client, seed_admin):
    from datetime import timedelta
    from sqlalchemy import update
    from sqlalchemy.orm import Session
    from aifootball.service.auth.models import AdminSession
    from aifootball.service.db import utcnow
    payload = {'login': 'admin', 'password': seed_admin['password']}
    assert client.post('/api/v1/auth/login', json=payload, headers={'Origin': 'https://foreign.example'}).status_code == 403
    r = client.post('/api/v1/auth/login', json=payload)
    assert r.status_code == 200
    with Session(client.app.state.engine) as db:
        db.execute(update(AdminSession).values(expires_at=utcnow()-timedelta(seconds=1)))
        db.commit()
    assert client.get('/api/v1/auth/me').status_code == 401
    for _ in range(10):
        assert client.post('/api/v1/auth/login', json={**payload, 'password': 'wrong'}).status_code == 401
    assert client.post('/api/v1/auth/login', json=payload).status_code == 429
