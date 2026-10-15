from io import BytesIO
from pathlib import Path
from uuid import uuid4
from PIL import Image
from fastapi.testclient import TestClient
from .test_team_profiles import create, update, player


def upload_png(client, color='blue'):
    image = BytesIO()
    Image.new('RGB', (12, 12), color).save(image, format='PNG')
    response = client.post('/api/v1/catalog/images', files={'file': ('logo.png', image.getvalue(), 'image/png')},
                           headers={'X-Request-ID': str(uuid4())})
    assert response.status_code == 201, response.text
    return response.json()['id']


def enter(client, tournament, team):
    response = client.post(f"/api/v1/tournaments/{tournament['id']}/entries", json={'team_id': team['id']})
    assert response.status_code == 201, response.text


def guest_get(client, image_id):
    with TestClient(client.app) as guest:
        return guest.get('/api/v1/public/catalog/team-logos/' + image_id)


def archive_tournament(client, tournament):
    current = client.get(f"/api/v1/tournaments/{tournament['id']}").json()
    response = client.patch(f"/api/v1/tournaments/{tournament['id']}",
                            json={'expected_revision': current['revision'], 'archived': True})
    assert response.status_code == 200, response.text


def test_visible_team_logo_is_public_with_safe_headers(admin_client, tournament_factory):
    logo = upload_png(admin_client)
    team, _ = create(admin_client, logo_id=logo)
    enter(admin_client, tournament_factory(), team)
    response = guest_get(admin_client, logo)
    assert response.status_code == 200
    assert response.headers['content-type'] == 'image/png'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['cache-control'] == 'no-store'
    with TestClient(admin_client.app) as guest:
        assert guest.get('/api/v1/catalog/images/' + logo).status_code == 401


def test_unlinked_photo_and_shared_images_stay_private(admin_client, tournament_factory):
    tournament = tournament_factory()
    unlinked = upload_png(admin_client, 'red')
    assert guest_get(admin_client, unlinked).status_code == 404
    assert guest_get(admin_client, str(uuid4())).status_code == 404
    photo = upload_png(admin_client, 'green')
    team, _ = create(admin_client, name='Фото', players=[player(photo_id=photo)])
    enter(admin_client, tournament, team)
    assert guest_get(admin_client, photo).status_code == 404
    shared = upload_png(admin_client, 'yellow')
    team, _ = create(admin_client, name='Общий', logo_id=shared, players=[player('Второй', photo_id=shared)])
    enter(admin_client, tournament, team)
    assert guest_get(admin_client, shared).status_code == 404
    unentered = upload_png(admin_client, 'purple')
    create(admin_client, name='Без заявки', logo_id=unentered)
    assert guest_get(admin_client, unentered).status_code == 404


def test_archived_links_close_logo_on_next_request(admin_client, tournament_factory):
    logo = upload_png(admin_client)
    visible, archived = tournament_factory(), tournament_factory(name='Архив')
    first, _ = create(admin_client, logo_id=logo)
    second, _ = create(admin_client, name='Юг', logo_id=logo)
    enter(admin_client, visible, first)
    enter(admin_client, archived, second)
    archive_tournament(admin_client, archived)
    assert guest_get(admin_client, logo).status_code == 200
    archive_tournament(admin_client, visible)
    assert guest_get(admin_client, logo).status_code == 404
    other = upload_png(admin_client, 'orange')
    team, _ = create(admin_client, name='Запад', logo_id=other)
    enter(admin_client, tournament_factory(name='Третий'), team)
    assert guest_get(admin_client, other).status_code == 200
    assert admin_client.patch(f"/api/v1/teams/{team['id']}", json={'archived': True}).status_code == 200
    assert guest_get(admin_client, other).status_code == 404


def test_missing_file_is_public_not_found(admin_client, tournament_factory):
    logo = upload_png(admin_client)
    team, _ = create(admin_client, logo_id=logo)
    enter(admin_client, tournament_factory(), team)
    root = Path(admin_client.app.state.settings.attachment_root) / 'catalog'
    (root / (logo + '.png')).unlink()
    assert guest_get(admin_client, logo).status_code == 404


def test_replaced_logo_is_no_longer_public(admin_client, tournament_factory):
    old = upload_png(admin_client)
    team, _ = create(admin_client, logo_id=old)
    enter(admin_client, tournament_factory(), team)
    new = upload_png(admin_client, 'black')
    response = update(admin_client, admin_client.get(f"/api/v1/teams/{team['id']}").json(), logo_id=new)
    assert response.status_code == 200, response.text
    assert guest_get(admin_client, old).status_code == 404
    assert guest_get(admin_client, new).status_code == 200
