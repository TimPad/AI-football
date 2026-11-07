from uuid import uuid4
from .test_stages_api import format_env, draw, fixtures, schedule, result  # noqa: F401


def test_remove_from_group_keeps_other_groups_matches(admin_client, format_env):
    env = format_env(teams=8, group_count=2, per_group=2)
    groups = env['stages'][0]
    stage = draw(admin_client, groups, method='snake', seeding=env['entries']).json()['stages'][0]
    other = next(f for f in fixtures(admin_client, env) if f['group_no'] == 2)
    kept = schedule(admin_client, env, other)
    victim = stage['draw']['placement'][0][0]
    body = {'op': 'remove', 'entry_id': victim, 'expected_revision': stage['revision']}
    preview = admin_client.post(f"/api/v1/stages/{groups['id']}/draw/adjust/preview", json=body).json()
    assert (preview['kept'], preview['cancelled']) == (1, 0)
    r = admin_client.post(f"/api/v1/stages/{groups['id']}/draw/adjust", json={**body, 'request_id': str(uuid4())})
    assert r.status_code == 200, r.text
    group_a = [f for f in fixtures(admin_client, env, unscheduled=False) if f['group_no'] == 1]
    assert len(group_a) == 3                                   # 3 команды — 3 пары
    assert admin_client.get(f"/api/v1/matches/{kept['id']}").json()['status'] == 'scheduled'


def test_add_late_team_to_smallest_group_and_bracket_bye(admin_client, format_env):
    env = format_env(template='playoff', teams=5)
    stage = draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries'][:4], participants=env['entries'][:4]).json()['stages'][0]
    r = admin_client.post(f"/api/v1/stages/{stage['id']}/draw/adjust",
                          json={'op': 'add', 'entry_id': env['entries'][4], 'expected_revision': stage['revision'], 'request_id': str(uuid4())})
    assert r.status_code == 409 and r.json()['error']['code'] == 'no_free_slot'   # сетка на 4 заполнена
    removed = admin_client.post(f"/api/v1/stages/{stage['id']}/draw/adjust", json={'op': 'remove', 'entry_id': env['entries'][3],
                                'expected_revision': stage['revision'], 'request_id': str(uuid4())}).json()['stages'][0]
    first = removed['sections'][0]['rounds'][0]['pairs']
    assert any(p['bye'] for p in first)                        # соперник убранной проходит дальше


def test_adjust_locked_after_start(admin_client, format_env, send_command):
    env = format_env(template='league', teams=4)
    stage = draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries']).json()['stages'][0]
    result(send_command, schedule(admin_client, env, fixtures(admin_client, env)[0]), 1, 0)
    r = admin_client.post(f"/api/v1/stages/{stage['id']}/draw/adjust", json={'op': 'remove', 'entry_id': env['entries'][0],
                          'expected_revision': stage['revision'], 'request_id': str(uuid4())})
    assert r.status_code == 409 and r.json()['error']['code'] == 'draw_locked'


def test_subset_participants(admin_client, format_env):
    env = format_env(template='league', teams=6)
    stage = env['stages'][0]
    chosen = env['entries'][:4]
    r = draw(admin_client, stage, method='seeded', seeding=chosen, participants=chosen)
    assert r.status_code == 200, r.text
    assert r.json()['stages'][0]['draw']['participants'] == chosen
    assert len(fixtures(admin_client, env)) == 6


def test_not_enough_teams_suggests_fix(admin_client, format_env):
    env = format_env(teams=7, group_count=4, per_group=2)
    groups = env['stages'][0]
    r = admin_client.post(f"/api/v1/stages/{groups['id']}/draw/preview", json={'method': 'pots', 'seed': 1})
    assert r.status_code == 422
    body = r.json()['error']
    assert body['code'] == 'not_enough_teams' and body['fields'] == {'group_count': '3'}
