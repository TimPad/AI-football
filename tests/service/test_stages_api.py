from uuid import uuid4
import pytest


@pytest.fixture
def format_env(admin_client, tournament_factory, regulation_data, hall_factory):
    def create(template='groups_playoff', teams=8, **params):
        t = tournament_factory()
        reg = admin_client.post(f"/api/v1/tournaments/{t['id']}/regulations", json={'variant_name': 'Основной', 'rules': regulation_data})
        assert reg.status_code == 201, reg.text
        entries = []
        for i in range(teams):
            team = admin_client.post('/api/v1/teams', json={'name': f'Команда {i + 1:02d}'}).json()
            r = admin_client.post(f"/api/v1/tournaments/{t['id']}/entries", json={'team_id': team['id']})
            assert r.status_code == 201, r.text
            entries.append(r.json()['id'])
        r = admin_client.post(f"/api/v1/tournaments/{t['id']}/format",
                              json={'template': template, 'regulation_id': reg.json()['id'], 'request_id': str(uuid4()), **params})
        assert r.status_code == 200, r.text
        hall = hall_factory()
        return {'tid': t['id'], 'entries': entries, 'stages': r.json()['stages'], 'reg': reg.json(),
                'slot': lambda: {'scheduled_at': '2026-11-01T18:00:00+03:00', 'hall_id': hall['id'], 'request_id': str(uuid4())}}
    return create


def draw(client, stage, **body):
    # participants передаётся как есть: «Кто играет» в жеребьёвке.
    body = {'method': 'seeded', 'seed': 0, 'seeding': [], 'expected_revision': stage['revision'], 'request_id': str(uuid4()), **body}
    return client.post(f"/api/v1/stages/{stage['id']}/draw", json=body)


def fixtures(client, env, unscheduled=True):
    return client.get(f"/api/v1/tournaments/{env['tid']}/fixtures?unscheduled={str(unscheduled).lower()}").json()['items']


def schedule(client, env, fixture):
    r = client.post(f"/api/v1/fixtures/{fixture['id']}/schedule", json=env['slot']())
    assert r.status_code == 201, r.text
    return r.json()


def result(send, match, home, away, confirm=True):
    r = send(match, 'set_totals', {'reported_totals': {'home': {'score': home}, 'away': {'score': away}}}); assert r.status_code == 200, r.text
    r = send(r.json(), 'set_status', {'status': 'ended'}); assert r.status_code == 200, r.text
    if confirm:
        r = send(r.json(), 'confirm', {'acknowledge_incomplete': True}); assert r.status_code == 200, r.text
    return r.json()


def publish(client, send, match):
    version = client.get(f"/api/v1/matches/{match['id']}/versions").json()['items'][0]
    r = send(match, 'publish', {'version_id': version['id']}); assert r.status_code == 200, r.text
    return r.json()


def stage_list(client, env):
    return client.get(f"/api/v1/tournaments/{env['tid']}/stages").json()['stages']


def play_all(client, env, send, score=lambda f: (1, 0), stage_id=None):
    """Назначает и подтверждает все пары, которые можно сыграть, пока такие есть."""
    for _ in range(20):
        ready = [f for f in fixtures(client, env) if f['can_schedule'] and (stage_id is None or f['stage_id'] == stage_id)]
        if not ready: return
        for f in ready: result(send, schedule(client, env, f), *score(f))


def test_groups_playoff_flow(admin_client, format_env, send_command):
    env = format_env(teams=8, group_count=2, per_group=2, third_place=True)
    groups, playoff = env['stages']
    preview = admin_client.post(f"/api/v1/stages/{groups['id']}/draw/preview", json={'method': 'pots', 'seed': 5, 'seeding': env['entries']})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert len(body['groups']) == 2 and body['pots'][env['entries'][0]] == 1 and body['pots'][env['entries'][7]] == 4
    assert not fixtures(admin_client, env)                       # предпросмотр ничего не записал
    placement = body['placement']; placement[0][0], placement[1][0] = placement[1][0], placement[0][0]
    request = str(uuid4())
    first = draw(admin_client, groups, method='manual', placement=placement, seeding=env['entries'], request_id=request)
    again = draw(admin_client, groups, method='manual', placement=placement, seeding=env['entries'], request_id=request)
    assert first.status_code == 200, first.text
    assert again.json() == first.json()
    stage = first.json()['stages'][0]
    assert stage['status'] == 'drawn' and stage['draw']['placement'] == placement
    assert len(fixtures(admin_client, env)) == 12
    scheme = draw(admin_client, playoff, method='scheme')
    assert scheme.status_code == 200, scheme.text
    semis = scheme.json()['stages'][1]['sections'][0]['rounds'][0]['pairs']
    assert [(p['home']['label'], p['away']['label']) for p in semis] == [('A1', 'B2'), ('B1', 'A2')]
    pending = fixtures(admin_client, env)
    semi = next(f for f in pending if f['key'] == 'U1-1')
    assert not semi['can_schedule']
    r = admin_client.post(f"/api/v1/fixtures/{semi['id']}/schedule", json=env['slot']())
    assert r.status_code == 422 and r.json()['error']['code'] == 'opponent_unknown'
    match = schedule(admin_client, env, next(f for f in pending if f['group_no'] == 1))
    assert match['stage_label'].startswith('Группа A · Тур')
    result(send_command, match, 2, 1)
    locked = draw(admin_client, stage, method='pots', seed=9, seeding=env['entries'])
    assert locked.status_code == 409 and locked.json()['error']['code'] == 'draw_locked'
    play_all(admin_client, env, send_command, stage_id=groups['id'])
    stages = stage_list(admin_client, env)
    assert stages[0]['status'] == 'completed'
    assert all(row['zone'] == 'advance' for g in stages[0]['groups'] for row in g['rows'][:2])
    play_all(admin_client, env, send_command)
    stages = stage_list(admin_client, env)
    assert stages[1]['status'] == 'completed'
    final_round = stages[1]['sections'][0]['rounds'][-1]
    assert {p['label'] for p in final_round['pairs']} == {'Финал', 'Матч за 3-е место'}
    assert all(p['winner'] for p in final_round['pairs'])


def test_redraw_keeps_matching_and_cancels_others(admin_client, format_env):
    env = format_env(template='league', teams=4)
    league = env['stages'][0]
    stage = draw(admin_client, league, method='seeded', seeding=env['entries']).json()['stages'][0]
    pending = fixtures(admin_client, env)
    kept = schedule(admin_client, env, next(f for f in pending if f['key'] == 'L-R1-1'))
    moved = schedule(admin_client, env, next(f for f in pending if f['key'] == 'L-R1-2'))
    e = env['entries']; order = [e[0], e[2], e[1], e[3]]             # первая пара тура 1 та же, во второй хозяин меняется
    preview = admin_client.post(f"/api/v1/stages/{league['id']}/draw/preview", json={'method': 'seeded', 'seeding': order}).json()
    assert (preview['kept'], preview['cancelled']) == (1, 1)
    r = draw(admin_client, stage, method='seeded', seeding=order)
    assert r.status_code == 200, r.text
    assert admin_client.get(f"/api/v1/matches/{kept['id']}").json()['status'] == 'scheduled'
    assert admin_client.get(f"/api/v1/matches/{moved['id']}").json()['status'] == 'cancelled'
    linked = [f for f in fixtures(admin_client, env, unscheduled=False) if f['match_id']]
    assert [f['match_id'] for f in linked] == [kept['id']]
    assert r.json()['stages'][0]['draw']['version'] == 2


def test_result_change_marks_fixture_and_replace(admin_client, format_env, send_command):
    env = format_env(template='playoff', teams=4)
    playoff = env['stages'][0]
    draw(admin_client, playoff, method='seeded', seeding=env['entries'])
    pending = fixtures(admin_client, env)
    first = schedule(admin_client, env, next(f for f in pending if f['key'] == 'U1-1'))
    second = schedule(admin_client, env, next(f for f in pending if f['key'] == 'U1-2'))
    first = result(send_command, first, 2, 0); result(send_command, second, 1, 0)
    final_fixture = next(f for f in fixtures(admin_client, env) if f['key'] == 'U2-1')
    final = schedule(admin_client, env, final_fixture)
    assert final['home_entry_id'] == env['entries'][0]
    reopened = send_command(first, 'reopen', {}).json()
    result(send_command, reopened, 0, 2)                         # победитель первой пары сменился
    pair = stage_list(admin_client, env)[0]['sections'][0]['rounds'][1]['pairs'][0]
    assert pair['changed'] and pair['note'] == 'Результат изменился'
    r = admin_client.post(f"/api/v1/fixtures/{final_fixture['id']}/replace",
                          json={'side': 'home', 'entry_id': env['entries'][3], 'request_id': str(uuid4())})
    assert r.status_code == 200, r.text
    assert r.json()['home_entry_id'] == env['entries'][3]
    assert not stage_list(admin_client, env)[0]['sections'][0]['rounds'][1]['pairs'][0]['changed']


def test_swiss_next_round_requires_results(admin_client, format_env, send_command):
    env = format_env(template='swiss', teams=6, rounds=3)
    swiss = env['stages'][0]
    stage = draw(admin_client, swiss, method='seeded', seeding=env['entries']).json()['stages'][0]
    early = admin_client.post(f"/api/v1/stages/{swiss['id']}/next-round", json={'expected_revision': stage['revision'], 'request_id': str(uuid4())})
    assert early.status_code == 409 and early.json()['error']['code'] == 'round_incomplete'
    played = set()
    for round_no in range(1, 4):
        current = [f for f in fixtures(admin_client, env) if f['round_no'] == round_no]
        for f in current:
            pair = frozenset((f['home']['team']['entry_id'], f['away']['team']['entry_id']))
            assert pair not in played; played.add(pair)
            result(send_command, schedule(admin_client, env, f), 1, 0)
        stage = stage_list(admin_client, env)[0]
        if round_no < 3:
            assert stage['can_next_round']
            r = admin_client.post(f"/api/v1/stages/{swiss['id']}/next-round", json={'expected_revision': stage['revision'], 'request_id': str(uuid4())})
            assert r.status_code == 200, r.text
    stage = stage_list(admin_client, env)[0]
    assert stage['status'] == 'completed' and not stage['can_next_round']


def test_lot_resolves_tie(admin_client, format_env, send_command):
    env = format_env(template='league', teams=3)
    league = env['stages'][0]
    draw(admin_client, league, method='seeded', seeding=env['entries'])
    play_all(admin_client, env, send_command, score=lambda f: (1, 0))
    stage = stage_list(admin_client, env)[0]
    group = stage['groups'][0]
    assert group['needs_lot'] and stage['status'] == 'completed'
    order = [row['team']['entry_id'] for row in group['rows']][::-1]
    r = admin_client.post(f"/api/v1/stages/{league['id']}/lots", json={'group': '1', 'order': order, 'request_id': str(uuid4())})
    assert r.status_code == 200, r.text
    group = r.json()['stages'][0]['groups'][0]
    assert not group['needs_lot'] and [row['team']['entry_id'] for row in group['rows']] == order


def test_format_locked_after_draw_and_double_elim(admin_client, format_env, send_command):
    env = format_env(template='double_elim', teams=5, grand_final_reset=True)
    stage = env['stages'][0]
    draw(admin_client, stage, method='random', seed=4, seeding=env['entries'])
    r = admin_client.post(f"/api/v1/tournaments/{env['tid']}/format",
                          json={'template': 'league', 'regulation_id': env['reg']['id'], 'request_id': str(uuid4())})
    assert r.status_code == 409 and r.json()['error']['code'] == 'format_locked'
    play_all(admin_client, env, send_command, score=lambda f: (0, 1) if f['key'] == 'F' else (1, 0))
    stage = stage_list(admin_client, env)[0]
    assert stage['status'] == 'completed'
    assert [s['key'] for s in stage['sections']] == ['upper', 'lower', 'final']
    assert [p['label'] for r in stage['sections'][2]['rounds'] for p in r['pairs']] == ['Гранд-финал', 'Переигровка финала']


def test_lot_is_asked_only_when_group_finished(admin_client, format_env, send_command):
    env = format_env(template='league', teams=3)
    draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries'])
    group = stage_list(admin_client, env)[0]['groups'][0]
    assert not group['needs_lot'] and not any(row['tied'] for row in group['rows'])   # никто не играл — жребий не нужен


def test_bracket_links_and_current_round(admin_client, format_env, send_command):
    env = format_env(template='playoff', teams=4)
    draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries'])
    section = stage_list(admin_client, env)[0]['sections'][0]
    assert section['current_round'] == 1
    final = section['rounds'][1]['pairs'][0]
    assert (final['home_from'], final['away_from']) == ('U1-1', 'U1-2')
    for key in ('U1-1', 'U1-2'):
        result(send_command, schedule(admin_client, env, next(f for f in fixtures(admin_client, env) if f['key'] == key)), 1, 0)
    assert stage_list(admin_client, env)[0]['sections'][0]['current_round'] == 2
