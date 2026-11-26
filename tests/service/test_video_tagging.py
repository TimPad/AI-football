"""Разметка ударов и защиты по видео в кабинете: закладки прогона и сводка для зрителя."""

import json
from uuid import uuid4

from .test_analysis_assignments import command
from .test_analysis_import import upload
from .test_analysis_jobs import analytics_match, new_job  # noqa: F401
from .test_auto_rating_sources import _protocol

BOARD = {
    'source': 'broadcast',
    'overlay': 'Мяч ТВ',
    'final': {'left': 1, 'right': 0},
    'goals': [{'t_s': 75.0, 'side': 'left', 'period': 1, 'elapsed_s': 75.0}],
}
SHOT = {'kind': 'shot', 'team': 'A', 'start_s': 40.0, 'on_target': True, 'confidence': 0.6}


def _run(client, match, publish=True):
    """Видеоанализ с табло, повтором и ударом-кандидатом; треки 1–2 — хозяева, 3 — гость."""
    from test_analysis_exchange import events_doc, result_zip

    def mutate(m, r, t, c):
        m.update(contract_version='3')
        r['scoreboard'] = BOARD
        c['camera_registration'] = {'share': {'ok': 0.9}, 'replays': [[80.0, 90.0]], 'keyframes': 10}

    events = json.loads(events_doc())
    events['candidates'] = [SHOT]
    job = new_job(client, match)
    run = upload(client, match, result_zip(job, mutate=mutate, extras={'events.json': json.dumps(events).encode()}))
    assert run.status_code == 200, run.text
    run = run.json()
    roster = run['context']['rosters']
    home = [p['player_id'] for p in roster if p['side'] == 'home']
    away = [p['player_id'] for p in roster if p['side'] == 'away']
    saved = client.put(
        f'/api/v1/matches/{match["id"]}/analysis/runs/{run["id"]}/assignments',
        json={
            'request_id': str(uuid4()),
            'expected_revision': run['revision'],
            'side_map': {'A': 'home', 'B': 'away'},
            'assignments': [{'track_id': 1, 'player_id': home[0]}, {'track_id': 3, 'player_id': away[0]}],
        },
    )
    assert saved.status_code == 200, saved.text
    run = command(client, match, saved.json(), 'confirm').json()
    if publish:
        run = command(client, match, run, 'publish').json()
    return run, home, away


def test_moments_give_halves_board_goals_replays_and_shot_candidates(admin_client, analytics_match):
    run, _, _ = _run(admin_client, analytics_match, publish=False)
    moments = admin_client.get(f'/api/v1/matches/{analytics_match["id"]}/analysis/runs/{run["id"]}/moments')
    assert moments.status_code == 200, moments.text
    assert moments.json() == {
        'run_id': run['id'],
        'video_s': 240.0,
        'halves': [[0.0, 240.0]],
        'side_map': {'A': 'home', 'B': 'away'},
        'board_final': {'left': 1, 'right': 0},
        'board_goals': [{'t_s': 75.0, 'plate': 'left'}],
        'replays': [[80.0, 90.0]],
        'shots': [{'t_s': 40.0, 'side': 'home', 'on_target': True}],
    }


def _tags(home, away, goal_id=None):
    """В створ (с сейвом гостя), мимо, заблокирован (блок гостя), отбор гостя (с проигранным единоборством хозяев)."""
    on, off, blocked = (str(uuid4()) for _ in range(3))
    at = lambda s: {'start_ms': s * 1000, 'end_ms': s * 1000}
    actions = [
        {
            'id': on,
            'kind': 'shot',
            'side': 'home',
            'player_id': home[0],
            'on_target': True,
            'outcome': 'saved',
            'start_xy': [30.0, 10.0],
            **at(40),
        },
        {'id': str(uuid4()), 'kind': 'save', 'side': 'away', 'outcome': 'success', 'success': True, **at(40)},
        {'id': off, 'kind': 'shot', 'side': 'home', 'on_target': False, 'outcome': 'off_target', **at(100)},
        {'id': blocked, 'kind': 'shot', 'side': 'home', 'outcome': 'failure', **at(150)},
        {'id': str(uuid4()), 'kind': 'shot_block', 'side': 'away', 'shot_id': blocked, **at(150)},
        {'id': str(uuid4()), 'kind': 'duel', 'side': 'away', 'success': True, 'outcome': 'success', **at(200)},
        {'id': str(uuid4()), 'kind': 'duel', 'side': 'home', 'success': False, 'outcome': 'failure', **at(200)},
        {'id': str(uuid4()), 'kind': 'recovery', 'side': 'away', **at(200)},
    ]
    links = []
    if goal_id:
        shot = str(uuid4())
        actions.append(
            {
                'id': shot,
                'kind': 'shot',
                'side': 'home',
                'on_target': True,
                'outcome': 'goal',
                'start_xy': [36.0, 10.0],
                **at(70),
            }
        )
        links.append({'kind': 'canonical', 'canonical_event_id': goal_id, 'source_event_id': shot})
    return actions, links


def _save(client, match, actions, links, status='confirmed', complete=True):
    overview = client.get(f'/api/v1/matches/{match["id"]}/performance-actions').json()
    current = overview['current']['document']
    # Разметка заменяет свои прежние действия: в версии, на которой она основана, они уже могут быть.
    ids = {a['id'] for a in actions}
    current = {**current, 'actions': [a for a in current['actions'] if a['id'] not in ids]}
    coverage = [{'status': 'complete' if complete else 'partial', 'intervals': None, 'player_ids': None}]
    doc = {
        **current,
        'actions': current['actions'] + actions,
        'links': current.get('links', []) + links,
        'completeness': {
            **current['completeness'],
            **{c: coverage for c in ('shots', 'saves', 'shot_blocks', 'duels', 'recoveries')},
        },
    }
    saved = client.put(
        f'/api/v1/matches/{match["id"]}/performance-actions',
        json={
            'request_id': str(uuid4()),
            'expected_revision': overview['revision'],
            'expected_match_revision': overview['match_revision'],
            'status': status,
            'document': doc,
        },
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


def _row(stats, key):
    return next(r for r in stats['rows'] if r['key'] == key)


def test_guest_sees_confirmed_tagging_before_actions_are_published(admin_client, analytics_match, send_command):
    match, _ = _protocol(admin_client, analytics_match, send_command)
    _, home, away = _run(admin_client, match)
    public = f'/api/v1/public/matches/{match["id"]}/action-stats'
    assert not any(r['category'] == 'shots' for r in admin_client.get(public).json()['rows'])
    actions, links = _tags(home, away)
    _save(admin_client, match, actions, links, status='review')  # черновик разметки зрителю не виден
    assert not any(r['category'] == 'shots' for r in admin_client.get(public).json()['rows'])
    _save(admin_client, match, actions, links)
    stats = admin_client.get(public).json()
    value = lambda key, side: _row(stats, key)[side]['value']
    assert [value(k, 'home') for k in ('shots_total', 'shots_on_target', 'shots_off_target', 'shots_blocked')] == [
        3,
        1,
        1,
        1,
    ]
    assert (value('saves', 'away'), value('shot_blocks', 'away'), value('recoveries', 'away')) == (1, 1, 1)
    duels = _row(stats, 'duels_won')
    assert (duels['away']['value'], duels['home']['value']) == (100.0, 0.0)
    assert {_row(stats, k)['source'] for k in ('shots_total', 'saves', 'duels_won')} == {'manual'}
    assert _row(stats, 'shots_total')['coverage'] == 'complete' and stats['coverage']['shots'] == 'complete'
    # Передачи остаются из видео; на карте ударов — удар с отмеченной точкой.
    assert _row(stats, 'passes_total')['source'] == 'cv_auto'
    assert [(s['x'], s['y'], s['on_target'], s['player_id']) for s in stats['shots']] == [(30.0, 10.0, True, home[0])]


def test_tagged_goal_links_to_the_protocol_goal(admin_client, analytics_match, send_command):
    goal = str(uuid4())
    added = send_command(
        analytics_match,
        'add_event',
        {'event': {'id': goal, 'kind': 'goal', 'side': 'home', 'period': 1, 'elapsed_ms': 60000}},
    )
    assert added.status_code == 200, added.text
    match, _ = _protocol(admin_client, added.json(), send_command)
    _, home, away = _run(admin_client, match)
    actions, links = _tags(home, away, goal_id=goal)
    _save(admin_client, match, actions, links, complete=False)
    stats = admin_client.get(f'/api/v1/public/matches/{match["id"]}/action-stats').json()
    # Гол — удар в створ; точка удара — из разметки, сам гол — из протокола.
    assert (_row(stats, 'shots_total')['home']['value'], _row(stats, 'shots_on_target')['home']['value']) == (4, 2)
    assert _row(stats, 'shots_total')['coverage'] == 'partial'
    goals = [s for s in stats['shots'] if s['goal']]
    assert [(s['x'], s['y']) for s in goals] == [(36.0, 10.0)]
