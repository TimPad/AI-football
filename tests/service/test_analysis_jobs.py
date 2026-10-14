from io import BytesIO
from zipfile import ZipFile
from uuid import uuid4
import json
import pytest
from sqlalchemy.orm import Session
from aifootball.service.auth.models import Admin
from .test_halls import create_hall, camera_body


def grant(client, enabled=True):
    with Session(client.app.state.engine) as db:
        admin = db.query(Admin).filter_by(login='admin').one()
        admin.can_manage_analytics = enabled
        db.commit()


@pytest.fixture
def analytics_match(admin_client, match_factory):
    grant(admin_client)
    hall = create_hall(admin_client)
    r = admin_client.post(f"/api/v1/halls/{hall['id']}/camera-profiles", json=camera_body(hall))
    assert r.status_code == 201, r.text
    return match_factory(hall_id=hall['id'], camera_profile_id=r.json()['id'])


def new_job(client, match):
    response = client.post(f"/api/v1/matches/{match['id']}/analysis/jobs", json={'request_id': str(uuid4())})
    assert response.status_code == 200, response.text
    return response.json()


def test_ordinary_admin_has_no_analytics_permission(admin_client, match_factory):
    assert admin_client.get('/api/v1/auth/me').json()['can_manage_analytics'] is False
    match = match_factory()
    response = admin_client.post(f"/api/v1/matches/{match['id']}/analysis/jobs", json={'request_id': str(uuid4())})
    assert response.status_code == 403


def test_job_context_export_and_retry(admin_client, analytics_match):
    path = f"/api/v1/matches/{analytics_match['id']}/analysis/jobs"
    body = {'request_id': str(uuid4())}
    first = admin_client.post(path, json=body)
    assert first.status_code == 200, first.text
    job = first.json()
    assert job['match_id'] == analytics_match['id']
    assert len(job['context']['rosters']) == 4
    assert job['context']['pitch'] == {'length_m': 41, 'width_m': 15.5}
    assert admin_client.post(path, json=body).json() == job
    archive = admin_client.get(path + f"/{job['id']}/package")
    assert archive.status_code == 200, archive.text
    with ZipFile(BytesIO(archive.content)) as zipped:
        contract = json.loads(zipped.read('job.json'))
        assert contract['contract_version'] == '1'
        assert contract['job_id'] == job['id']
        assert contract['context_hash'] == job['context_hash']
        assert 'homography.json' in zipped.namelist()
        assert 'match.mp4' not in zipped.namelist()


def test_context_ignores_schedule_but_tracks_lineup(admin_client, analytics_match, send_command):
    job = new_job(admin_client, analytics_match)
    changed = send_command(analytics_match, 'update_match', {'scheduled_at': '2026-10-21T18:00:00+03:00'})
    assert changed.status_code == 200, changed.text
    other = new_job(admin_client, changed.json())
    assert other['context_hash'] == job['context_hash']
    from aifootball.service.matches.models import LineupMember
    with Session(admin_client.app.state.engine) as db:
        member = db.query(LineupMember).filter_by(match_id=analytics_match['id']).first()
        member.shirt_number = '99'
        db.commit()
    assert new_job(admin_client, changed.json())['context_hash'] != job['context_hash']


def test_missing_camera_and_revoked_capability(admin_client, analytics_match, match_factory):
    no_camera = match_factory()
    path = f"/api/v1/matches/{no_camera['id']}/analysis/jobs"
    assert admin_client.post(path, json={'request_id': str(uuid4())}).status_code == 422
    grant(admin_client, False)
    assert admin_client.get('/api/v1/auth/me').json()['can_manage_analytics'] is False
    assert admin_client.post(path, json={'request_id': str(uuid4())}).status_code == 403


def test_significant_context_hash():
    from aifootball.service.analysis.context import context_hash
    context = {'pitch': {'length_m': 40, 'width_m': 20}, 'rosters': []}
    assert context_hash(context) == context_hash(dict(context))
    assert context_hash(context) != context_hash({**context, 'rosters': [{'player_id': 'p1'}]})
