from uuid import uuid4


def tournament_body(**changes):
    return {'request_id': str(uuid4()), 'name': 'Новый кубок', 'season': '2026',
            'starts_on': '2026-10-01', 'ends_on': '2026-12-31', **changes}


def person(name, number=None):
    return {'player_id': str(uuid4()), 'name': name, 'shirt_number': number}


def test_create_tournament_retry_returns_same_id(admin_client):
    body = tournament_body()
    first = admin_client.post('/api/v1/tournaments', json=body)
    assert first.status_code == 201, first.text
    assert admin_client.post('/api/v1/tournaments', json=body).json() == first.json()
    assert admin_client.get('/api/v1/tournaments').json()['total'] == 1
    assert admin_client.post('/api/v1/tournaments', json={**body, 'name': 'Другое имя'}).status_code == 409
    current = first.json()
    assert admin_client.patch(f"/api/v1/tournaments/{current['id']}", json={
        'expected_revision': current['revision'], 'name': 'Исправлено'}).status_code == 200


def test_regulation_retry_keeps_one_version(admin_client, tournament_factory, regulation_data):
    tournament = tournament_factory()
    url = f"/api/v1/tournaments/{tournament['id']}/regulations"
    body = {'request_id': str(uuid4()), 'variant_name': 'Основной', 'rules': regulation_data}
    first = admin_client.post(url, json=body)
    assert first.status_code == 201, first.text
    assert admin_client.post(url, json=body).json() == first.json()
    assert admin_client.get(url).json()['total'] == 1
    assert admin_client.post(url, json={**body, 'variant_name': 'Другой'}).status_code == 409


def test_create_team_entry_is_atomic_and_retryable(admin_client, tournament_factory):
    tournament = tournament_factory()
    body = {'request_id': str(uuid4()), 'expected_tournament_revision': tournament['revision'],
            'team': {'request_id': str(uuid4()), 'name': 'Север',
                     'players': [person('Первый', '7'), person('Второй', '9')]}}
    url = f"/api/v1/tournaments/{tournament['id']}/teams"
    first = admin_client.post(url, json=body)
    assert first.status_code == 201, first.text
    assert admin_client.post(url, json=body).json() == first.json()
    roster = admin_client.get(f"/api/v1/entries/{first.json()['id']}/players").json()
    assert {row['player_id'] for row in roster['players']} == {row['player_id'] for row in body['team']['players']}
    assert admin_client.get('/api/v1/teams').json()['total'] == 1
    assert admin_client.get('/api/v1/players').json()['total'] == 2


def test_team_entry_retry_does_not_require_nested_request_id(admin_client, tournament_factory):
    tournament = tournament_factory()
    body = {'request_id': str(uuid4()), 'expected_tournament_revision': tournament['revision'],
            'team': {'name': 'Запад', 'players': [person('Игрок')]}}
    url = f"/api/v1/tournaments/{tournament['id']}/teams"
    first = admin_client.post(url, json=body)
    assert first.status_code == 201, first.text
    repeated = admin_client.post(url, json=body)
    assert repeated.status_code == 201, repeated.text
    assert repeated.json() == first.json()


def test_failed_entry_rolls_back_new_team_and_people(admin_client, tournament_factory, regulation_data):
    tournament = tournament_factory()
    admin_client.post(f"/api/v1/tournaments/{tournament['id']}/regulations", json={
        'variant_name': 'Малый', 'rules': {**regulation_data, 'players_on_pitch': 1,
                                         'match_roster_limit': 1, 'tournament_roster_limit': 1}})
    body = {'request_id': str(uuid4()), 'expected_tournament_revision': tournament['revision'],
            'team': {'name': 'Не создана', 'players': [person('Первый'), person('Второй')]}}
    result = admin_client.post(f"/api/v1/tournaments/{tournament['id']}/teams", json=body)
    assert result.status_code == 422, result.text
    assert admin_client.get('/api/v1/teams').json()['total'] == 0
    assert admin_client.get('/api/v1/players').json()['total'] == 0
    assert admin_client.get(f"/api/v1/tournaments/{tournament['id']}/entries").json()['total'] == 0


def test_batch_entries_retry_and_failure_are_atomic(admin_client, tournament_factory, regulation_data):
    tournament = tournament_factory()
    teams = [admin_client.post('/api/v1/teams', json={
        'name': name, 'players': [person(name + ' 1'), person(name + ' 2')]}).json()
        for name in ('Север', 'Юг')]
    url = f"/api/v1/tournaments/{tournament['id']}/entries/batch"
    body = {'request_id': str(uuid4()), 'expected_tournament_revision': tournament['revision'],
            'team_ids': [team['id'] for team in teams]}
    first = admin_client.post(url, json=body)
    assert first.status_code == 201, first.text
    assert len(first.json()) == 2
    assert admin_client.post(url, json=body).json() == first.json()
    assert admin_client.get(f"/api/v1/tournaments/{tournament['id']}/entries").json()['total'] == 2
    other = tournament_factory(name='Другой кубок')
    admin_client.post(f"/api/v1/tournaments/{other['id']}/regulations", json={
        'variant_name': 'Малый', 'rules': {**regulation_data, 'players_on_pitch': 1,
                                         'match_roster_limit': 1, 'tournament_roster_limit': 1}})
    body = {**body, 'request_id': str(uuid4()), 'expected_tournament_revision': other['revision']}
    assert admin_client.post(f"/api/v1/tournaments/{other['id']}/entries/batch", json=body).status_code == 422
    assert admin_client.get(f"/api/v1/tournaments/{other['id']}/entries").json()['total'] == 0
