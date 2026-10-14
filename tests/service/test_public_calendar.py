from fastapi.testclient import TestClient
from .test_confirmation import finish


def test_guest_calendar_is_narrow_and_filters_local_day(admin_client, match_factory):
    m = match_factory(scheduled_at='2026-10-19T22:30:00Z', venue_label='Зал 1')
    with TestClient(admin_client.app) as guest:
        tournaments = guest.get('/api/v1/public/tournaments')
        assert tournaments.status_code == 200
        assert tournaments.json()['items'][0]['id'] == m['tournament_id']
        url = f"/api/v1/public/tournaments/{m['tournament_id']}/matches"
        assert guest.get(url + '?day=2026-10-19').json()['total'] == 0
        response = guest.get(url + '?day=2026-10-20')
        assert response.status_code == 200
        item = response.json()['items'][0]
        assert item['home_name'] == 'Север' and item['venue_label'] == 'Зал 1'
        assert item['score'] == {'home': None, 'away': None}
        assert item['schedule_slot_s'] == 5400
        assert not {'protocol', 'clock', 'referees', 'lineup', 'revision'} & item.keys()
        assert guest.get('/api/v1/matches/' + m['id']).status_code == 401


def test_public_result_uses_only_published_snapshot(admin_client, match_factory, send_command):
    m = finish(send_command, match_factory())
    m = send_command(m, 'set_notes', {'notes': 'PRIVATE SECRET'}).json()
    m = send_command(m, 'confirm', {'acknowledge_incomplete': True}).json()
    version = admin_client.get(f"/api/v1/matches/{m['id']}/versions").json()['items'][0]
    m = send_command(m, 'publish', {'version_id': version['id']}).json()
    m = send_command(m, 'reopen', {}).json()
    m = send_command(m, 'set_totals', {'reported_totals': {'home': {'score': 9}, 'away': {'score': 2}}}).json()
    with TestClient(admin_client.app) as guest:
        url = '/api/v1/public/matches/' + m['id']
        response = guest.get(url)
        assert response.status_code == 200
        assert response.json()['score'] == {'home': 3, 'away': 2}
        assert response.json()['public_protocol_id']
        assert 'PRIVATE SECRET' not in response.text
        assert send_command(m, 'unpublish', {}).status_code == 200
        assert guest.get(url).json()['score'] == {'home': None, 'away': None}
    assert admin_client.patch('/api/v1/tournaments/' + m['tournament_id'], json={'expected_revision': 0, 'archived': True}).status_code == 200
    with TestClient(admin_client.app) as guest:
        assert guest.get('/api/v1/public/tournaments').json()['total'] == 0
        assert guest.get('/api/v1/public/matches/' + m['id']).status_code == 404


def test_broadcast_urls_validate_persist_clear_and_retry(admin_client, match_factory, send_command):
    m = match_factory()
    url = 'https://vk.com/video-123_456'
    embed = 'https://vk.com/video_ext.php?oid=-123&id=456&hash=abc'
    from uuid import uuid4
    key = str(uuid4())
    payload = {'broadcast_url': url, 'broadcast_embed_url': embed}
    first = send_command(m, 'update_match', payload, key)
    assert first.status_code == 200, first.text
    assert send_command(m, 'update_match', payload, key).json() == first.json()
    saved = first.json()
    with TestClient(admin_client.app) as guest:
        item = guest.get('/api/v1/public/matches/' + m['id']).json()
        assert item['broadcast_url'] == url and item['broadcast_embed_url'] == embed
    for bad in ['javascript:alert(1)', 'https://vk.com.evil.test/video_ext.php?oid=1&id=2', 'https://vk.com/feed', 'https://user@vk.com/video_ext.php?oid=1&id=2', 'https://vk.com/video_ext.php?oid=x&id=2']:
        assert send_command(saved, 'update_match', {'broadcast_embed_url': bad}).status_code == 422
    assert send_command(saved, 'update_match', {'broadcast_url': 'https://example.com'}).status_code == 422
    cleared = send_command(saved, 'update_match', {'broadcast_url': None, 'broadcast_embed_url': None})
    assert cleared.status_code == 200
    assert cleared.json()['broadcast_url'] is None
    created = match_factory(broadcast_url=url, broadcast_embed_url=embed)
    assert created['broadcast_embed_url'] == embed
