from io import BytesIO
from uuid import uuid4
from PIL import Image
from fastapi.testclient import TestClient


def player(name='Иван Петров', **changes):
    return {'player_id': str(uuid4()), 'name': name, 'birth_date': '2000-06-15',
            'position': 'goalkeeper', 'height_cm': 182, 'weight_kg': 78.5,
            'shirt_number': '1', **changes}


def create(client, **changes):
    data = {'request_id': str(uuid4()), 'name': 'Север', 'description': 'Команда города',
            'players': [player()], **changes}
    response = client.post('/api/v1/teams', json=data)
    assert response.status_code == 201, response.text
    return response.json(), data


def update(client, team, **changes):
    data = {'request_id': str(uuid4()), 'expected_revision': team['revision'],
            'name': team['name'], 'description': team['description'], 'logo_id': team['logo_id'],
            'players': [{**row['player'], 'player_id': row['player_id'], 'shirt_number': row['shirt_number']}
                        for row in team['players']], **changes}
    for row in data['players']:
        for field in ['id', 'created_at', 'archived']:
            row.pop(field, None)
    return client.put(f"/api/v1/teams/{team['id']}/profile", json=data)


def test_team_creation_is_atomic_retryable_and_seeds_tournament(admin_client, tournament_factory):
    team, data = create(admin_client)
    repeat = admin_client.post('/api/v1/teams', json=data)
    assert repeat.status_code == 201 and repeat.json() == team
    assert admin_client.get('/api/v1/players').json()['total'] == 1
    member = team['players'][0]
    assert member['player_id'] == data['players'][0]['player_id']
    assert member['player']['height_cm'] == 182 and member['player']['position'] == 'goalkeeper'
    assert admin_client.get(f"/api/v1/teams/{team['id']}").json() == team
    tid = tournament_factory()['id']
    entry = admin_client.post(f'/api/v1/tournaments/{tid}/entries', json={'team_id': team['id']}).json()
    roster = admin_client.get(f"/api/v1/entries/{entry['id']}/players").json()
    assert roster['players'][0]['player_id'] == member['player_id']
    assert roster['players'][0]['shirt_number'] == '1'
    with TestClient(admin_client.app) as guest:
        assert guest.get(f"/api/v1/teams/{team['id']}").status_code == 401


def test_profile_validation_rolls_back_and_existing_player_is_reused(admin_client):
    key = str(uuid4())
    invalid = admin_client.post('/api/v1/teams', json={'request_id': key, 'name': 'Invalid',
        'players': [player(), player('Второй')]})
    assert invalid.status_code == 422
    assert admin_client.get('/api/v1/teams').json()['total'] == 0
    assert admin_client.get('/api/v1/players').json()['total'] == 0
    existing = admin_client.post('/api/v1/players', json={'name': 'Игрок'}).json()
    member = player('Игрок', player_id=existing['id'], revision=existing['revision'])
    team, _ = create(admin_client, players=[member])
    assert admin_client.get('/api/v1/players').json()['total'] == 1
    changed = update(admin_client, team, description='Новое описание')
    assert changed.status_code == 200
    assert update(admin_client, team).status_code == 409
    assert update(admin_client, changed.json(), players=[]).status_code == 200
    assert admin_client.get('/api/v1/players').json()['total'] == 1
    for field, value in [('birth_date', '2999-01-01'), ('height_cm', -1), ('weight_kg', 0), ('position', 'unknown')]:
        assert admin_client.post('/api/v1/teams', json={'name': 'Bad', 'players': [player(**{field: value})]}).status_code == 422


def test_player_edit_does_not_rewrite_match_identity(admin_client, match_factory):
    m = match_factory()
    person = admin_client.get('/api/v1/players').json()['items'][0]
    assert admin_client.patch('/api/v1/players/' + person['id'], json={'name': 'Новое ФИО', 'height_cm': 190}).status_code == 200
    saved = admin_client.get('/api/v1/matches/' + m['id']).json()
    assert saved['lineup'] == m['lineup']
    assert person['id'] in [row['player_id'] for row in saved['lineup']]


def test_profile_images_validate_decode_and_stay_private(admin_client):
    image = BytesIO()
    Image.new('RGB', (30, 20), 'red').save(image, format='PNG')
    key = str(uuid4())
    endpoint = '/api/v1/catalog/images'
    headers = {'X-Request-ID': key}
    response = admin_client.post(endpoint, files={'file': ('photo.png', image.getvalue(), 'image/png')}, headers=headers)
    assert response.status_code == 201, response.text
    media = response.json()
    assert admin_client.post(endpoint, files={'file': ('photo.png', image.getvalue(), 'image/png')}, headers=headers).json() == media
    downloaded = admin_client.get(endpoint + '/' + media['id'])
    assert downloaded.status_code == 200 and downloaded.headers['content-type'] == 'image/png'
    assert Image.open(BytesIO(downloaded.content)).size == (30, 20)
    team, _ = create(admin_client, logo_id=media['id'], players=[player(photo_id=media['id'])])
    assert team['logo_id'] == media['id'] and team['players'][0]['player']['photo_id'] == media['id']
    assert admin_client.post(endpoint, files={'file': ('bad.png', b'not a png', 'image/png')}, headers={'X-Request-ID': str(uuid4())}).status_code == 422
    assert admin_client.post('/api/v1/teams', json={'name': 'Missing', 'logo_id': str(uuid4())}).status_code == 404
    with TestClient(admin_client.app) as guest:
        assert guest.get(endpoint + '/' + media['id']).status_code == 401


def test_conflicting_player_profile_rolls_back_whole_team(admin_client):
    team, _ = create(admin_client, players=[player('Первый', shirt_number='1'), player('Второй', shirt_number='2')])
    member = team['players'][0]
    assert admin_client.patch('/api/v1/players/' + member['player_id'], json={'name': 'Правка в другом окне'}).status_code == 200
    changed = update(admin_client, team, name='Не должно сохраниться')
    assert changed.status_code == 409
    saved = admin_client.get('/api/v1/teams/' + team['id']).json()
    assert saved['name'] == team['name'] and saved['revision'] == team['revision']
    assert len(saved['players']) == 2


def test_team_roster_changes_preserve_existing_tournament_roster(admin_client, tournament_factory):
    team, _ = create(admin_client)
    tid = tournament_factory()['id']
    entry = admin_client.post(f'/api/v1/tournaments/{tid}/entries', json={'team_id': team['id']}).json()
    roster_before = admin_client.get(f"/api/v1/entries/{entry['id']}/players").json()
    assert update(admin_client, team, players=[]).status_code == 200
    assert admin_client.get(f"/api/v1/entries/{entry['id']}/players").json()['players'] == roster_before['players']


def test_changed_creation_request_cannot_duplicate_team(admin_client):
    team, data = create(admin_client)
    assert admin_client.post('/api/v1/teams', json={**data, 'name': 'Другой'}).status_code == 409
    assert admin_client.get('/api/v1/teams').json()['total'] == 1
    assert admin_client.get('/api/v1/teams/' + team['id']).json()['name'] == data['name']
