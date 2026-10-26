from uuid import uuid4
from fastapi.testclient import TestClient
from .test_confirmation import finish
from .test_stages_api import format_env, draw, fixtures, schedule, result, publish  # noqa: F401


def test_public_standings_only_published(admin_client, format_env, send_command):
    env = format_env(template='playoff', teams=4)
    draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries'])
    first = result(send_command, schedule(admin_client, env, next(f for f in fixtures(admin_client, env) if f['key'] == 'U1-1')), 3, 1)
    with TestClient(admin_client.app) as guest:
        url = f"/api/v1/public/tournaments/{env['tid']}"
        semi = guest.get(url + '/standings').json()['stages'][0]['sections'][0]['rounds'][0]['pairs'][0]
        assert semi['winner'] is None and semi['legs'][0]['score'] is None and semi['legs'][0]['fixture_id'] is None
        final = guest.get(url + '/standings').json()['stages'][0]['sections'][0]['rounds'][1]['pairs'][0]
        assert final['home']['team'] is None and final['home']['label'] == 'Победитель пары 1'
        publish(admin_client, send_command, first)
        stage = guest.get(url + '/standings').json()['stages'][0]
        assert stage['sections'][0]['rounds'][0]['pairs'][0]['winner'] == 'home'
        assert stage['sections'][0]['rounds'][1]['pairs'][0]['home']['team']['entry_id'] == env['entries'][0]
        assert 'config' not in stage or stage['config'] is None
        unscheduled = guest.get(url + '/fixtures').json()['items']
        assert {f['key'] for f in unscheduled} == {'U1-2', 'U2-1'} and not any(f['can_schedule'] for f in unscheduled)


def test_draft_stage_hidden_from_viewer(admin_client, format_env):
    env = format_env(template='league', teams=4)
    with TestClient(admin_client.app) as guest:
        assert guest.get(f"/api/v1/public/tournaments/{env['tid']}/standings").json() == {'implicit': False, 'stages': []}


def test_formatless_tournament_has_implicit_table_and_can_hide(admin_client, match_factory, send_command):
    m = send_command(finish(send_command, match_factory()), 'confirm', {'acknowledge_incomplete': True}).json()
    publish(admin_client, send_command, m)
    with TestClient(admin_client.app) as guest:
        url = f"/api/v1/public/tournaments/{m['tournament_id']}/standings"
        body = guest.get(url).json()
        assert body['implicit'] and body['stages'][0]['groups'][0]['rows'][0]['points'] == 3
        assert body['stages'][0]['groups'][0]['rows'][0]['team']['name'] == 'Север'
        # Кабинетный список этапов не выдаёт общую таблицу за этап: формат ещё можно выбрать.
        assert admin_client.get(f"/api/v1/tournaments/{m['tournament_id']}/stages").json() == {'implicit': False, 'stages': []}
        assert admin_client.get(f"/api/v1/tournaments/{m['tournament_id']}/standings").json()['implicit']
        t = admin_client.get(f"/api/v1/tournaments/{m['tournament_id']}").json()
        r = admin_client.patch(f"/api/v1/tournaments/{t['id']}", json={'expected_revision': t['revision'], 'standings_public': False})
        assert r.status_code == 200, r.text
        assert guest.get(url).json()['stages'] == []
        assert guest.get(f"/api/v1/public/tournaments/{t['id']}").json()['standings_public'] is False
