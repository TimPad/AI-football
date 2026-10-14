from uuid import uuid4
import copy
from sqlalchemy.orm import Session
from .test_analysis_jobs import analytics_match, new_job, grant
from .test_analysis_import import upload
from test_analysis_exchange import result_zip


def import_run(client, match, mutate=None):
    job = new_job(client, match)
    response = upload(client, match, result_zip(job, mutate=mutate))
    assert response.status_code == 200, response.text
    return response.json()


def assignments(run, overlap=False):
    home = next(p['player_id'] for p in run['context']['rosters'] if p['side'] == 'home')
    away = next(p['player_id'] for p in run['context']['rosters'] if p['side'] == 'away')
    return [{'track_id': 1, 'player_id': home}, {'track_id': 2, 'player_id': home}, {'track_id': 3, 'player_id': away}]


def save_assignments(client, match, run, values=None):
    return client.put(f"/api/v1/matches/{match['id']}/analysis/runs/{run['id']}/assignments", json={
        'request_id': str(uuid4()), 'expected_revision': run['revision'],
        'side_map': {'A': 'home', 'B': 'away'}, 'assignments': values if values is not None else assignments(run)})


def command(client, match, run, kind, request_id=None, analysis_revision=None):
    if analysis_revision is None:
        analysis_revision = client.get(f"/api/v1/matches/{match['id']}/analysis").json()['analysis_revision']
    return client.post(f"/api/v1/matches/{match['id']}/analysis/runs/{run['id']}/{kind}", json={
        'request_id': request_id or str(uuid4()), 'expected_revision': run['revision'],
        'expected_analysis_revision': analysis_revision})


def test_confirm_identity_aggregate_and_idempotence(admin_client, analytics_match):
    run = import_run(admin_client, analytics_match)
    saved = save_assignments(admin_client, analytics_match, run)
    assert saved.status_code == 200, saved.text
    run = saved.json()
    request_id = str(uuid4())
    confirmed = command(admin_client, analytics_match, run, 'confirm', request_id, 0)
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()
    home = next(p for p in result['players'] if p['side'] == 'home')
    assert home['metrics']['distance_m'] == 210
    assert home['metrics']['observed_s'] == 180
    assert home['metrics']['m_per_min'] == 70
    assert len(home['track_ids']) == 2
    assert command(admin_client, analytics_match, run, 'confirm', request_id, 0).json() == result
    assert save_assignments(admin_client, analytics_match, result).status_code == 409
    history = admin_client.get(f"/api/v1/players/{home['player_id']}/analysis").json()
    assert history['match_count'] == 1
    assert history['matches'][0]['metrics']['distance_m'] == 210


def test_overlapping_fragments_block_confirm_without_erasing_prior(admin_client, analytics_match):
    def overlap(m, r, t, c): t['tracks'][1]['intervals'] = [[30, 150]]
    run = import_run(admin_client, analytics_match, overlap)
    saved = save_assignments(admin_client, analytics_match, run)
    assert saved.status_code == 200, saved.text
    assert command(admin_client, analytics_match, saved.json(), 'confirm').status_code == 422
    assert admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis").json()['active_run_id'] is None
    values = assignments(run); values[1] = {'track_id': 2, 'excluded_reason': 'Дублирующий трек'}
    corrected = save_assignments(admin_client, analytics_match, saved.json(), values)
    assert corrected.status_code == 200
    assert command(admin_client, analytics_match, corrected.json(), 'confirm').status_code == 200


def test_foreign_identity_side_and_stale_revision(admin_client, analytics_match):
    run = import_run(admin_client, analytics_match)
    values = assignments(run); values[0]['player_id'] = str(uuid4())
    assert save_assignments(admin_client, analytics_match, run, values).status_code == 422
    values = assignments(run); values[0]['player_id'] = values[2]['player_id']
    assert save_assignments(admin_client, analytics_match, run, values).status_code == 422
    saved = save_assignments(admin_client, analytics_match, run)
    assert saved.status_code == 200
    assert save_assignments(admin_client, analytics_match, run).status_code == 409


def test_critical_quality_and_ordinary_admin_cannot_confirm(admin_client, analytics_match):
    def bad(m, r, t, c): c.update(passed=False, critical_errors=['Камера не прошла проверку'])
    run = import_run(admin_client, analytics_match, bad)
    saved = save_assignments(admin_client, analytics_match, run).json()
    assert command(admin_client, analytics_match, saved, 'confirm').status_code == 422
    grant(admin_client, False)
    assert command(admin_client, analytics_match, saved, 'confirm').status_code == 403


def test_average_from_sums_and_unknown_not_zero():
    from aifootball.service.analysis.aggregation import aggregate_player
    first = {'distance_m': 120, 'observed_s': 60, 'hsr_m': 10, 'sprints': 1, 'vmax_ms': 5}
    second = {'distance_m': 90, 'observed_s': 180, 'hsr_m': 10, 'sprints': 1, 'vmax_ms': 4}
    assert aggregate_player([first, second])['m_per_min'] == 52.5
    assert aggregate_player([])['distance_m'] is None


def test_player_history_has_catalog_detail(admin_client, analytics_match):
    person = analytics_match['lineup'][0]['player_id']
    response = admin_client.get(f'/api/v1/players/{person}')
    assert response.status_code == 200
    assert response.json()['id'] == person
