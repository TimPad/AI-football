from uuid import uuid4
from fastapi.testclient import TestClient
from test_roster_xlsx import book


def upload(client, target, rows, scope='tournament', entry_id=None):
    data={'scope': scope, 'target_id': target}
    if entry_id:
        data['entry_id']=entry_id
    response = client.post('/api/v1/roster-imports', data=data,
        files={'file': ('состав.xlsx', book(rows), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert response.status_code == 201, response.text
    return response.json()


def preview(client, source, mapping, **changes):
    body = {'expected_revision': source['revision'], 'sheet': source['sheets'][0]['name'],
            'mapping': mapping, **changes}
    response = client.put(f"/api/v1/roster-imports/{source['id']}/preview", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def commit(client, state, **changes):
    return client.post(f"/api/v1/roster-imports/{state['id']}/commit", json={
        'request_id': str(uuid4()), 'expected_revision': state['revision'], **changes})


def test_import_three_teams_and_45_players_is_atomic_and_retryable(admin_client, tournament_factory):
    tournament = tournament_factory()
    rows = [['Команда', 'ФИО', 'Номер']] + [[f'Команда {team}', f'Игрок {team}-{i}', str(i)]
        for team in range(3) for i in range(1, 16)]
    source = upload(admin_client, tournament['id'], rows)
    assert admin_client.get('/api/v1/players').json()['total'] == 0
    state = preview(admin_client, source, {'team': 0, 'name': 1, 'shirt_number': 2})
    assert state['can_commit'] and state['summary']['players_created'] == 45
    request_id = str(uuid4())
    first = commit(admin_client, state, request_id=request_id)
    assert first.status_code == 200, first.text
    assert first.json()['teams_created'] == 3 and first.json()['players_created'] == 45
    assert commit(admin_client, state, request_id=request_id).json() == first.json()
    assert admin_client.get('/api/v1/players?limit=100').json()['total'] == 45
    entries = admin_client.get(f"/api/v1/tournaments/{tournament['id']}/entries").json()['items']
    assert len(entries) == 3
    for entry in entries:
        assert len(admin_client.get(f"/api/v1/entries/{entry['id']}/players").json()['players']) == 15


def test_duplicate_number_can_be_fixed_or_row_excluded(admin_client, tournament_factory):
    source = upload(admin_client, tournament_factory()['id'], [
        ['Команда', 'ФИО', 'Номер'], ['Север', 'Первый', '7'], ['Север', 'Второй', '7']])
    mapping = {'team': 0, 'name': 1, 'shirt_number': 2}
    state = preview(admin_client, source, mapping)
    assert not state['can_commit']
    assert commit(admin_client, state).status_code == 422
    state = preview(admin_client, state, mapping, edits={state['rows'][1]['id']: {'shirt_number': '8'}})
    assert state['can_commit']
    result = commit(admin_client, state)
    assert result.status_code == 200 and result.json()['players_created'] == 2


def test_matching_player_is_explicit_and_profile_is_not_overwritten(admin_client):
    team = admin_client.post('/api/v1/teams', json={'name': 'Север'}).json()
    player = admin_client.post('/api/v1/players', json={'name': 'Иван Тест', 'height_cm': 180}).json()
    source = upload(admin_client, team['id'], [['ФИО', 'Рост, см'], ['Иван Тест', 195]], 'team')
    state = preview(admin_client, source, {'name': 0, 'height_cm': 1})
    assert not state['can_commit'] and state['rows'][0]['player_candidates'][0]['id'] == player['id']
    state = preview(admin_client, state, {'name': 0, 'height_cm': 1},
                    decisions={state['rows'][0]['id']: {'player_id': player['id']}})
    assert state['can_commit']
    result = commit(admin_client, state)
    assert result.status_code == 200 and result.json()['players_reused'] == 1
    assert admin_client.get(f"/api/v1/players/{player['id']}").json()['height_cm'] == 180


def test_append_preserves_roster_and_stale_preview_is_not_applied(admin_client):
    first_id = str(uuid4())
    team = admin_client.post('/api/v1/teams', json={'name': 'Север', 'players': [
        {'player_id': first_id, 'name': 'Первый', 'shirt_number': '7'}]}).json()
    source = upload(admin_client, team['id'], [['ФИО', 'Номер'], ['Новый', '9']], 'team')
    state = preview(admin_client, source, {'name': 0, 'shirt_number': 1})
    admin_client.patch(f"/api/v1/teams/{team['id']}", json={'description': 'Параллельная правка'})
    assert commit(admin_client, state).status_code == 409
    assert admin_client.get('/api/v1/players').json()['total'] == 1
    state = preview(admin_client, state, {'name': 0, 'shirt_number': 1})
    assert commit(admin_client, state).status_code == 200
    players = admin_client.get(f"/api/v1/teams/{team['id']}").json()['players']
    assert len(players) == 2 and first_id in {row['player_id'] for row in players}


def test_excluded_row_report_and_formula_validation(admin_client, tournament_factory):
    source = upload(admin_client, tournament_factory()['id'], [
        ['Команда', 'ФИО', 'Номер'], ['Север', 'Правильный', '07'], ['Север', 'Формула', '=2+5']])
    mapping = {'team': 0, 'name': 1, 'shirt_number': 2}
    state = preview(admin_client, source, mapping)
    assert not state['can_commit'] and state['rows'][1]['source_row'] == 3
    state = preview(admin_client, state, mapping, excluded_rows=[state['rows'][1]['id']])
    assert state['can_commit']
    assert admin_client.get(f"/api/v1/roster-imports/{source['id']}/report").status_code == 200
    result = commit(admin_client, state)
    assert result.status_code == 200 and result.json()['skipped_rows'] == 1


def test_tournament_import_adds_only_entry_not_permanent_members(admin_client, tournament_factory):
    team = admin_client.post('/api/v1/teams', json={'name': 'Север'}).json()
    tournament = tournament_factory()
    source = upload(admin_client, tournament['id'], [['Команда', 'ФИО'], ['Север', 'Новый']])
    state = preview(admin_client, source, {'team': 0, 'name': 1})
    assert not state['can_commit']
    state = preview(admin_client, state, {'team': 0, 'name': 1}, team_decisions={'Север': team['id']})
    assert commit(admin_client, state).status_code == 200
    assert admin_client.get(f"/api/v1/teams/{team['id']}").json()['players'] == []
    entry = admin_client.get(f"/api/v1/tournaments/{tournament['id']}/entries").json()['items'][0]
    assert len(admin_client.get(f"/api/v1/entries/{entry['id']}/players").json()['players']) == 1


def test_archive_and_private_preview_are_guarded(admin_client, tournament_factory):
    from sqlalchemy.orm import Session
    from aifootball.service.auth.cli import create_admin
    tournament = tournament_factory()
    source = upload(admin_client, tournament['id'], [['Команда', 'ФИО'], ['Север', 'Новый']])
    with TestClient(admin_client.app) as guest:
        assert guest.get(f"/api/v1/roster-imports/{source['id']}").status_code == 401
    with Session(admin_client.app.state.engine) as db:
        create_admin(db, 'other-admin', 'test-other-password')
    with TestClient(admin_client.app) as other:
        other.headers['Origin'] = admin_client.headers['Origin']
        assert other.post('/api/v1/auth/login', json={'login': 'other-admin', 'password': 'test-other-password'}).status_code == 200
        assert other.get(f"/api/v1/roster-imports/{source['id']}").status_code == 404
    state = preview(admin_client, source, {'team': 0, 'name': 1})
    admin_client.patch(f"/api/v1/tournaments/{tournament['id']}", json={'expected_revision': tournament['revision'], 'archived': True})
    assert commit(admin_client, state).status_code in (409, 422)


def test_roster_limit_blocks_all_teams_before_any_write(admin_client, tournament_factory, regulation_data):
    tournament = tournament_factory()
    admin_client.post(f"/api/v1/tournaments/{tournament['id']}/regulations", json={
        'variant_name': 'Лимит', 'rules': {**regulation_data, 'players_on_pitch': 1,
                                         'match_roster_limit': 1, 'tournament_roster_limit': 1}})
    source = upload(admin_client, tournament['id'], [
        ['Команда', 'ФИО'], ['Север', 'Первый'], ['Юг', 'Второй'], ['Юг', 'Третий']])
    state = preview(admin_client, source, {'team': 0, 'name': 1})
    assert not state['can_commit']
    assert commit(admin_client, state).status_code == 422
    assert admin_client.get('/api/v1/players').json()['total'] == 0
    assert admin_client.get('/api/v1/teams').json()['total'] == 0


def test_expired_preview_is_private_but_committed_replay_survives_cleanup(admin_client):
    from datetime import timedelta
    from sqlalchemy.orm import Session
    from aifootball.service.db import utcnow
    from aifootball.service.catalog.roster_imports.models import RosterImport
    from aifootball.service.catalog.roster_imports.cleanup import cleanup
    team = admin_client.post('/api/v1/teams', json={'name': 'Север'}).json()
    source = upload(admin_client, team['id'], [['ФИО'], ['Первый']], 'team')
    state = preview(admin_client, source, {'name': 0})
    request_id = str(uuid4())
    first = commit(admin_client, state, request_id=request_id)
    assert first.status_code == 200
    with Session(admin_client.app.state.engine) as db, db.begin():
        item = db.get(RosterImport, state['id'])
        item.expires_at = utcnow() - timedelta(days=1)
        db.flush()
        cleanup(db)
    assert commit(admin_client, state, request_id=request_id).json() == first.json()
    source = upload(admin_client, team['id'], [['ФИО'], ['Второй']], 'team')
    with Session(admin_client.app.state.engine) as db, db.begin():
        db.get(RosterImport, source['id']).expires_at = utcnow() - timedelta(days=1)
    assert admin_client.get(f"/api/v1/roster-imports/{source['id']}").status_code == 410


def test_excel_request_is_bounded_before_multipart_parsing(admin_client):
    result = admin_client.post('/api/v1/roster-imports', content=b'x', headers={
        'Content-Type': 'multipart/form-data; boundary=bad', 'Content-Length': str(6 * 1024 * 1024 + 1)})
    assert result.status_code == 413


def test_one_entry_import_needs_no_team_column(admin_client, tournament_factory):
    tournament = tournament_factory()
    team = admin_client.post('/api/v1/teams', json={'name': 'Север'}).json()
    entry = admin_client.post(f"/api/v1/tournaments/{tournament['id']}/entries", json={'team_id': team['id']}).json()
    source = upload(admin_client, tournament['id'], [['ФИО', 'Номер'], ['Первый', '7']], entry_id=entry['id'])
    state = preview(admin_client, source, {'name': 0, 'shirt_number': 1})
    assert state['can_commit']
    assert commit(admin_client, state).status_code == 200
    assert len(admin_client.get(f"/api/v1/entries/{entry['id']}/players").json()['players']) == 1
    assert admin_client.get(f"/api/v1/teams/{team['id']}").json()['players'] == []
