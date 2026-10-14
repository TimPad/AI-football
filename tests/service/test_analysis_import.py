from uuid import uuid4
import copy
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from aifootball.service.analysis.models import AnalysisRun
from .test_analysis_jobs import analytics_match, new_job, grant
from test_analysis_exchange import result_zip


def upload(client, match, package, request_id=None):
    return client.post(f"/api/v1/matches/{match['id']}/analysis/imports",
                       files={'file': ('result.zip', package, 'application/zip')},
                       headers={'X-Request-ID': request_id or str(uuid4())})


def test_import_retry_content_dedup_and_same_uuid_conflict(admin_client, analytics_match):
    job = new_job(admin_client, analytics_match); package = result_zip(job)
    request_id = str(uuid4())
    first = upload(admin_client, analytics_match, package, request_id)
    assert first.status_code == 200, first.text
    assert first.json()['status'] == 'review'
    assert 'storage_key' not in first.json()
    assert upload(admin_client, analytics_match, package, request_id).json() == first.json()
    assert upload(admin_client, analytics_match, package).json()['id'] == first.json()['id']
    assert upload(admin_client, analytics_match, result_zip(job), request_id).status_code == 409
    with Session(admin_client.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(AnalysisRun)) == 1
    assert admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis").json()['active_run_id'] is None


@pytest.mark.parametrize('change', ['match', 'job', 'context', 'pitch', 'camera', 'resolution'])
def test_wrong_result_context_rejected(admin_client, analytics_match, change):
    job = new_job(admin_client, analytics_match)
    def mutate(m, r, t, c):
        if change == 'match': m['match_id'] = str(uuid4())
        if change == 'job': m['job_id'] = str(uuid4())
        if change == 'context': m['context_hash'] = 'f' * 64
        if change == 'camera': m['camera_profile_id'] = str(uuid4())
        if change == 'resolution': m['source_video']['width'] = 2000
        if change == 'pitch': r['pitch']['length_m'] = 42
    response = upload(admin_client, analytics_match, result_zip(job, mutate=mutate))
    assert response.status_code in (404, 422), response.text
    with Session(admin_client.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(AnalysisRun)) == 0


def test_changed_roster_but_not_schedule_and_permissions(admin_client, analytics_match, send_command):
    job = new_job(admin_client, analytics_match); package = result_zip(job)
    changed = send_command(analytics_match, 'update_match', {'scheduled_at': '2026-10-21T18:00:00+03:00'}).json()
    assert upload(admin_client, changed, package).status_code == 200
    from aifootball.service.matches.models import LineupMember
    with Session(admin_client.app.state.engine) as db:
        db.query(LineupMember).filter_by(match_id=analytics_match['id']).first().shirt_number = '99'
        db.commit()
    assert upload(admin_client, changed, result_zip(job)).status_code == 422
    grant(admin_client, False)
    assert upload(admin_client, changed, package).status_code == 403
    assert admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis").status_code == 200


def test_import_limits_and_unknown_track_leave_no_artifacts(admin_client, analytics_match, monkeypatch):
    job = new_job(admin_client, analytics_match)
    root = admin_client.app.state.settings.attachment_root / 'analysis'
    before = set(root.glob('*.zip')) if root.exists() else set()
    bad = result_zip(job, mutate=lambda m, r, t, c: r['periods'][0]['players'][0].update(track_id=999))
    assert upload(admin_client, analytics_match, bad).status_code == 422
    monkeypatch.setattr(admin_client.app.state.settings, 'analysis_zip_limit', 100)
    assert upload(admin_client, analytics_match, result_zip(job)).status_code == 413
    assert (set(root.glob('*.zip')) if root.exists() else set()) == before


def test_import_request_is_bounded_before_multipart_spooling(admin_client, analytics_match, monkeypatch):
    settings=admin_client.app.state.settings
    monkeypatch.setattr(settings,'analysis_zip_limit',100)
    r=admin_client.post(f"/api/v1/matches/{analytics_match['id']}/analysis/imports",headers={'Content-Length':str(2*1024*1024)},content=b'x')
    assert r.status_code==413
