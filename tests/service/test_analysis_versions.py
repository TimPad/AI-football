from uuid import uuid4
from fastapi.testclient import TestClient
from .test_analysis_jobs import analytics_match
from .test_analysis_assignments import import_run, save_assignments, command


def confirm(client, match, run):
    saved = save_assignments(client, match, run)
    assert saved.status_code == 200, saved.text
    response = command(client, match, saved.json(), 'confirm')
    assert response.status_code == 200, response.text
    return response.json()


def test_new_version_one_match_and_separate_publication(admin_client, analytics_match):
    old = confirm(admin_client, analytics_match, import_run(admin_client, analytics_match))
    pub = command(admin_client, analytics_match, old, 'publish')
    assert pub.status_code == 200, pub.text
    public_path = f"/api/v1/public/matches/{analytics_match['id']}/analysis"
    with TestClient(admin_client.app) as guest:
        visible = guest.get(public_path)
        assert visible.status_code == 200
        assert visible.json()['run_id'] == old['id']
        assert 'tracks' not in visible.json() and 'manifest' not in visible.json()
        def change(m, r, t, c): r['periods'][0]['players'][0]['distance_m'] = 150
        new = confirm(admin_client, analytics_match, import_run(admin_client, analytics_match, change))
        assert guest.get(public_path).json()['run_id'] == old['id']
        pid = new['players'][0]['player_id']
        history = admin_client.get(f'/api/v1/players/{pid}/analysis').json()
        assert history['match_count'] == 1 and history['matches'][0]['run_id'] == new['id']
        assert command(admin_client, analytics_match, new, 'publish').status_code == 200
        assert guest.get(public_path).json()['run_id'] == new['id']
        assert guest.get(f"/api/v1/matches/{analytics_match['id']}/analysis").status_code == 401


def test_stale_pointer_command_and_manual_review_clone(admin_client, analytics_match):
    old = confirm(admin_client, analytics_match, import_run(admin_client, analytics_match))
    before = admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis").json()['analysis_revision']
    newer = confirm(admin_client, analytics_match, import_run(admin_client, analytics_match))
    assert command(admin_client, analytics_match, old, 'publish', analysis_revision=before).status_code == 409
    response = command(admin_client, analytics_match, old, 'reviews')
    assert response.status_code == 200, response.text
    review = response.json()
    assert review['id'] != old['id'] and review['source_run_id'] == old['id']
    assert review['status'] == 'review' and len(review['assignments']) == 3
    assert review['players'] == []
    assert admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis/runs/{old['id']}").json()['status'] == 'confirmed'
    assert command(admin_client, analytics_match, newer, 'activate').status_code == 200


def test_public_team_missing_data_retains_quality(admin_client,analytics_match):
    def missing(m,r,t,c):
        r['pitch']['private_path']='Приватная папка обработчика'
        r['periods'][0]['teams']={'B':{'distance_m':None,'observed_s':None,'hsr_m':None,'sprints':None,'heatmap_s':None,'low_data':True,'metric_notes':{'distance_m':'Приватная служебная заметка'}}}
    run=import_run(admin_client,analytics_match,missing)
    run=save_assignments(admin_client,analytics_match,run).json()
    run=command(admin_client,analytics_match,run,'confirm').json()
    assert command(admin_client,analytics_match,run,'publish').status_code==200
    public=admin_client.get(f"/api/v1/public/matches/{analytics_match['id']}/analysis").json()
    team=public['periods'][0]['teams']['B']
    assert team['distance_m'] is None and team['low_data'] is True
    assert team['metric_notes']['distance_m']=='Нет наблюдений команды'
    assert 'Приватная' not in str(public)
