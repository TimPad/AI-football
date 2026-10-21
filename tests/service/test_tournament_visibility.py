"""Visibility applies to every published child, including direct public IDs."""
from fastapi.testclient import TestClient

from .test_confirmation import finish
from .test_analysis_jobs import analytics_match
from .test_analysis_assignments import import_run, save_assignments, command


def visibility(client, tournament_id, value):
    current = client.get(f'/api/v1/tournaments/{tournament_id}').json()
    response = client.patch(f'/api/v1/tournaments/{tournament_id}', json={
        'expected_revision': current['revision'], 'visibility': value})
    assert response.status_code == 200, response.text
    return response.json()


def test_new_tournament_is_private_until_explicit_publication(admin_client):
    response = admin_client.post('/api/v1/tournaments', json={
        'name': 'Неопубликованный кубок', 'season': '2026',
        'starts_on': '2026-10-01', 'ends_on': '2026-12-31'})
    assert response.status_code == 201, response.text
    tournament = response.json()
    assert tournament['visibility'] == 'draft'
    with TestClient(admin_client.app) as guest:
        assert guest.get('/api/v1/public/tournaments').json()['total'] == 0
        assert guest.get(f"/api/v1/public/tournaments/{tournament['id']}").status_code == 404
        published = visibility(admin_client, tournament['id'], 'public')
        assert published['revision'] == tournament['revision'] + 1
        assert guest.get('/api/v1/public/tournaments').json()['total'] == 1
        assert guest.get(f"/api/v1/public/tournaments/{tournament['id']}").status_code == 200
        assert admin_client.patch(f"/api/v1/tournaments/{tournament['id']}", json={
            'expected_revision': 0, 'visibility': 'draft'}).status_code == 409


def test_hidden_tournament_blocks_direct_protocol_and_match(admin_client, match_factory, send_command):
    match = finish(send_command, match_factory())
    match = send_command(match, 'confirm', {'acknowledge_incomplete': True}).json()
    version = admin_client.get(f"/api/v1/matches/{match['id']}/versions").json()['items'][0]
    match = send_command(match, 'publish', {'version_id': version['id']}).json()
    version = admin_client.get(f"/api/v1/matches/{match['id']}/versions").json()['items'][0]
    public_paths = [
        f"/api/v1/public/tournaments/{match['tournament_id']}/matches",
        f"/api/v1/public/matches/{match['id']}",
        f"/api/v1/public/protocols/{version['public_id']}",
    ]
    with TestClient(admin_client.app) as guest:
        assert all(guest.get(path).status_code == 200 for path in public_paths)
        published_protocol = guest.get(public_paths[-1]).json()
        visibility(admin_client, match['tournament_id'], 'draft')
        for path in public_paths:
            assert guest.get(path).status_code == 404, path
        assert admin_client.get(f"/api/v1/matches/{match['id']}").json()['published_version_id'] == version['id']
        visibility(admin_client, match['tournament_id'], 'public')
        assert guest.get(public_paths[-1]).json() == published_protocol


def test_hidden_tournament_blocks_cv_and_all_rating_readers(admin_client, analytics_match):
    match = analytics_match
    run = import_run(admin_client, match)
    run = save_assignments(admin_client, match, run).json()
    run = command(admin_client, match, run, 'confirm').json()
    assert command(admin_client, match, run, 'publish').status_code == 200
    pid = run['players'][0]['player_id']
    public_paths = [
        f"/api/v1/public/matches/{match['id']}/analysis",
        f"/api/v1/public/tournaments/{match['tournament_id']}/ratings",
        f"/api/v1/public/players/{pid}/ratings?tournament_id={match['tournament_id']}",
        f"/api/v1/public/matches/{match['id']}/ratings",
    ]
    with TestClient(admin_client.app) as guest:
        assert all(guest.get(path).status_code == 200 for path in public_paths)
        visibility(admin_client, match['tournament_id'], 'draft')
        for path in public_paths + [f"/api/v1/public/matches/{match['id']}/action-stats"]:
            assert guest.get(path).status_code == 404, path
        current = admin_client.get(f"/api/v1/matches/{match['id']}").json()
        assert current['published_analysis_run_id'] == run['id']


def test_archiving_also_blocks_published_protocol(admin_client, match_factory, send_command):
    match = finish(send_command, match_factory())
    match = send_command(match, 'confirm', {'acknowledge_incomplete': True}).json()
    version = admin_client.get(f"/api/v1/matches/{match['id']}/versions").json()['items'][0]
    send_command(match, 'publish', {'version_id': version['id']})
    version = admin_client.get(f"/api/v1/matches/{match['id']}/versions").json()['items'][0]
    current = admin_client.get(f"/api/v1/tournaments/{match['tournament_id']}").json()
    assert admin_client.patch(f"/api/v1/tournaments/{match['tournament_id']}", json={
        'expected_revision': current['revision'], 'archived': True}).status_code == 200
    with TestClient(admin_client.app) as guest:
        assert guest.get(f"/api/v1/public/protocols/{version['public_id']}").status_code == 404
