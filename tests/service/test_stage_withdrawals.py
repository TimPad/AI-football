from uuid import uuid4
from .test_stages_api import format_env, draw, fixtures, schedule, result, stage_list  # noqa: F401


def own(client, env, team, unscheduled=True):
    return [f for f in fixtures(client, env, unscheduled) if team in (f['home']['team'] or {}).get('entry_id', '') + (f['away']['team'] or {}).get('entry_id', '')]


def withdraw(client, env, stage_id, team, **extra):
    revision = next(s for s in stage_list(client, env) if s['id'] == stage_id)['revision']
    return client.post(f"/api/v1/stages/{stage_id}/withdrawals", json={'entry_id': team, 'expected_revision': revision,
                                                                      'request_id': str(uuid4()), **extra})


def test_half_rule_annuls_before_half(admin_client, format_env, send_command):
    env = format_env(template='league', teams=6)                       # у каждой команды 5 матчей
    stage = draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries']).json()['stages'][0]
    team = env['entries'][0]
    for f in own(admin_client, env, team)[:2]: result(send_command, schedule(admin_client, env, f), 1, 0)
    pending = schedule(admin_client, env, own(admin_client, env, team)[0])   # назначен, но не сыгран
    preview = admin_client.post(f"/api/v1/stages/{stage['id']}/withdrawals/preview", json={'entry_id': team}).json()
    assert (preview['played'], preview['total'], preview['rule'], preview['annulled'], preview['cancelled_matches']) == (2, 5, 'annul', 5, 1)
    r = withdraw(admin_client, env, stage['id'], team)
    assert r.status_code == 200, r.text
    body = r.json()['stages'][0]
    assert team not in [row['team']['entry_id'] for row in body['groups'][0]['rows']]
    assert body['withdrawn'] == [{'team': body['withdrawn'][0]['team'], 'rule': 'annul'}]
    assert sum(row['played'] for row in body['groups'][0]['rows']) == 0   # оба сыгранных матча были с ней — аннулированы
    assert admin_client.get(f"/api/v1/matches/{pending['id']}").json()['status'] == 'cancelled'
    again = withdraw(admin_client, env, stage['id'], team)
    assert again.status_code == 409 and again.json()['error']['code'] == 'already_withdrawn'


def test_half_rule_walkovers_from_half(admin_client, format_env, send_command):
    env = format_env(template='league', teams=7)                       # 6 матчей у команды, сыграно 3
    stage = draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries']).json()['stages'][0]
    team = env['entries'][0]
    for f in own(admin_client, env, team)[:3]: result(send_command, schedule(admin_client, env, f), 2, 2)
    preview = admin_client.post(f"/api/v1/stages/{stage['id']}/withdrawals/preview", json={'entry_id': team}).json()
    assert (preview['played'], preview['total'], preview['rule'], preview['walkovers']) == (3, 6, 'walkover', 3)
    body = withdraw(admin_client, env, stage['id'], team).json()['stages'][0]
    rows = body['groups'][0]['rows']
    assert rows[-1]['team']['entry_id'] == team and rows[-1]['played'] == 6
    assert rows[-1]['goals_against'] == 6 + 15 and rows[-1]['lost'] == 3
    technical = [l for r in body['sections'][0]['rounds'] for p in r['pairs'] for l in p['legs'] if l['technical']]
    assert len(technical) == 3 and all(sorted(l['score'].values()) == [0, 5] for l in technical)
    assert not own(admin_client, env, team)                            # пар без даты у снятой команды не осталось


def test_annul_chosen_explicitly_overrides_half_rule(admin_client, format_env, send_command):
    env = format_env(template='league', teams=5)                       # 4 матча, сыграно 2 → по правилу технические
    stage = draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries']).json()['stages'][0]
    team = env['entries'][1]
    for f in own(admin_client, env, team)[:2]: result(send_command, schedule(admin_client, env, f), 1, 0)
    preview = admin_client.post(f"/api/v1/stages/{stage['id']}/withdrawals/preview", json={'entry_id': team, 'rule': 'annul'}).json()
    assert (preview['default_rule'], preview['rule']) == ('walkover', 'annul')
    body = withdraw(admin_client, env, stage['id'], team, rule='annul').json()['stages'][0]
    assert team not in [row['team']['entry_id'] for row in body['groups'][0]['rows']]


def test_bracket_withdrawal_gives_walkover(admin_client, format_env, send_command):
    env = format_env(template='playoff', teams=4)
    stage = draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries']).json()['stages'][0]
    first = next(f for f in fixtures(admin_client, env) if f['key'] == 'U1-1')
    second = next(f for f in fixtures(admin_client, env) if f['key'] == 'U1-2')
    result(send_command, schedule(admin_client, env, first), 3, 0)
    pending = schedule(admin_client, env, second)
    team = pending['away_entry_id']
    body = withdraw(admin_client, env, stage['id'], team).json()['stages'][0]
    semi = body['sections'][0]['rounds'][0]['pairs'][1]
    assert semi['walkover'] == 'home' and semi['winner'] == 'home'
    final = body['sections'][0]['rounds'][1]['pairs'][0]
    assert final['away']['team']['entry_id'] == pending['home_entry_id']
    assert admin_client.get(f"/api/v1/matches/{pending['id']}").json()['status'] == 'cancelled'
    assert body['withdrawn'][0]['rule'] == 'elimination'


def test_swiss_withdrawn_team_skips_next_rounds(admin_client, format_env, send_command):
    env = format_env(template='swiss', teams=6, rounds=3)
    stage = draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries']).json()['stages'][0]
    current = [f for f in fixtures(admin_client, env) if f['round_no'] == 1]
    result(send_command, schedule(admin_client, env, current[0]), 1, 0)
    team = current[1]['home']['team']['entry_id']
    body = withdraw(admin_client, env, stage['id'], team).json()['stages'][0]
    for f in [f for f in fixtures(admin_client, env) if f['round_no'] == 1]: result(send_command, schedule(admin_client, env, f), 1, 0)
    stage = stage_list(admin_client, env)[0]
    assert stage['can_next_round']
    r = admin_client.post(f"/api/v1/stages/{stage['id']}/next-round", json={'expected_revision': stage['revision'], 'request_id': str(uuid4())})
    assert r.status_code == 200, r.text
    second = [f for f in fixtures(admin_client, env) if f['round_no'] == 2]
    assert team not in [f['home']['team']['entry_id'] for f in second] + [f['away']['team']['entry_id'] for f in second]


def test_withdrawal_before_start_points_to_adjust(admin_client, format_env):
    env = format_env(template='league', teams=4)
    stage = draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries']).json()['stages'][0]
    r = admin_client.post(f"/api/v1/stages/{stage['id']}/withdrawals/preview", json={'entry_id': env['entries'][0]})
    assert r.status_code == 409 and r.json()['error']['code'] == 'use_adjust'


def test_settled_pairs_leave_unscheduled_list(admin_client, format_env, send_command):
    env = format_env(template='playoff', teams=4)
    stage = draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries']).json()['stages'][0]
    result(send_command, schedule(admin_client, env, next(f for f in fixtures(admin_client, env) if f['key'] == 'U1-1')), 1, 0)
    team = next(f for f in fixtures(admin_client, env) if f['key'] == 'U1-2')['away']['team']['entry_id']
    withdraw(admin_client, env, stage['id'], team)
    keys = [f['key'] for f in fixtures(admin_client, env)]
    assert 'U1-2' not in keys and 'U2-1' in keys
    assert next(f for f in fixtures(admin_client, env) if f['key'] == 'U2-1')['can_schedule']
