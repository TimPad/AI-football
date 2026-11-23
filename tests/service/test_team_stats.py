from uuid import uuid4

from .test_analysis_jobs import analytics_match, grant  # noqa: F401
from .test_events import event
from .test_ratings_snapshots import publish_sources


def _setup(client, match, send, actions, completeness):
    """Протокол с одним голом, подтверждённые участие и действия с заданными записями."""
    home = [p['player_id'] for p in match['lineup'] if p['side'] == 'home']
    away = [p['player_id'] for p in match['lineup'] if p['side'] == 'away']
    goal = event(player_id=home[0], assist_known=True, elapsed_ms=300000)
    for kind, payload in [
        ('add_event', {'event': goal}),
        ('set_completeness', {'goals': 'complete', 'assists': 'complete', 'fouls': 'complete', 'cards': 'complete'}),
        ('set_status', {'status': 'ended'}),
        ('confirm', {'acknowledge_incomplete': True}),
    ]:
        response = send(match, kind, payload)
        assert response.status_code == 200, response.text
        match = response.json()
    protocol = client.get(f'/api/v1/matches/{match["id"]}/versions').json()['items'][0]
    doc = {
        'clock_basis': 'game',
        'time_basis': 'reviewed_effective',
        'analysis_scope': 'full_match',
        'duration_ms': 2400000,
        'source_protocol_version_id': protocol['id'],
        'initial_five': {'home': [], 'away': []},
        'play_intervals': [[0, 2400000]],
        'players': [
            {
                'player_id': p['player_id'],
                'presence': [[0, 2400000]],
                'roles': [{'role': 'ala', 'intervals': [[0, 2400000]]}],
                'completeness': 'complete',
                'appeared': True,
            }
            for p in match['lineup']
        ],
    }
    part = client.put(
        f'/api/v1/matches/{match["id"]}/participation',
        json={
            'request_id': str(uuid4()),
            'expected_revision': 0,
            'expected_match_revision': match['revision'],
            'status': 'confirmed',
            'document': doc,
        },
    )
    assert part.status_code == 200, part.text
    adoc = {
        'clock_basis': 'game',
        'analysis_scope': 'full_match',
        'duration_ms': 2400000,
        'source_participation_version_id': part.json()['id'],
        'source_protocol_version_id': protocol['id'],
        'actions': actions(home, away),
        'completeness': completeness,
    }
    saved = client.put(
        f'/api/v1/matches/{match["id"]}/performance-actions',
        json={
            'request_id': str(uuid4()),
            'expected_revision': 0,
            'expected_match_revision': match['revision'],
            'status': 'confirmed',
            'document': adoc,
        },
    )
    assert saved.status_code == 200, saved.text
    return match, protocol, part.json(), saved.json()


def _actions(home, away):
    shot = lambda **c: {
        'id': str(uuid4()),
        'kind': 'shot',
        'player_id': home[1],
        'side': 'home',
        'start_ms': 60000,
        **c,
    }
    blocked = shot(on_target=False, outcome='failure', start_xy=[30.0, 8.0])
    return [
        shot(on_target=True, outcome='saved', start_xy=[34.0, 9.0]),
        shot(on_target=False, outcome='off_target', start_ms=1500000),
        blocked,
        {
            'id': str(uuid4()),
            'kind': 'shot_block',
            'player_id': away[0],
            'side': 'away',
            'start_ms': 60000,
            'shot_id': blocked['id'],
        },
        *[
            {'id': str(uuid4()), 'kind': 'pass', 'player_id': home[0], 'side': 'home', 'start_ms': 100000, 'success': s}
            for s in (True, True, False, None)
        ],
        {
            'id': str(uuid4()),
            'kind': 'duel',
            'player_id': away[0],
            'side': 'away',
            'start_ms': 1300000,
            'success': True,
        },
        {'id': str(uuid4()), 'kind': 'save', 'player_id': away[0], 'side': 'away', 'start_ms': 60000},
    ]


def _row(stats, key):
    return next(r for r in stats['rows'] if r['key'] == key)


def test_team_stats_count_outcomes_keep_unknown_and_skip_undeclared(admin_client, analytics_match, send_command):
    match, _, _, _ = _setup(
        admin_client,
        analytics_match,  # noqa: F401
        send_command,
        _actions,
        {'shots': [{'status': 'complete'}], 'passes': [{'status': 'partial', 'intervals': [[0, 600000]]}]},
    )
    response = admin_client.get(f'/api/v1/matches/{match["id"]}/action-stats')
    assert response.status_code == 200, response.text
    stats = response.json()
    assert stats['source']['published'] is False and stats['source']['status'] == 'confirmed'
    # Гол протокола — тоже удар в створ; заблокированный удар не считается «мимо».
    assert _row(stats, 'shots_total')['home']['value'] == 4 and _row(stats, 'shots_on_target')['home']['value'] == 2
    assert _row(stats, 'shots_off_target')['home']['value'] == 1 and _row(stats, 'shots_blocked')['home']['value'] == 1
    assert _row(stats, 'shots_total')['coverage'] == 'complete'
    passes = _row(stats, 'passes_accurate')['home']
    assert (passes['numerator'], passes['denominator'], passes['unknown']) == (2, 3, 1)
    assert passes['value'] == 66.7 and _row(stats, 'passes_accurate')['coverage'] == 'partial'
    # Запись без объявленной полноты показывается, категория без записей и объявления — нет.
    assert _row(stats, 'duels_won')['away']['value'] == 100.0 and _row(stats, 'duels_won')['coverage'] == 'unknown'
    assert all(r['key'] != 'recoveries' for r in stats['rows'])
    assert {s['outcome'] for s in stats['shots']} == {'saved', 'failure'} and all(
        s['side'] == 'home' for s in stats['shots']
    )
    assert stats['pitch'] is not None and [p['key'] for p in stats['periods']] == ['all', '1', '2']
    # Передачи без точек на карту не попадают, но входят в сводку исполнителя: неизвестный исход — не в точности.
    home = [p['player_id'] for p in match['lineup'] if p['side'] == 'home']
    assert stats['passes'] == []
    assert stats['pass_players'] == [
        {'side': 'home', 'player_id': home[0], 'total': 4, 'accurate': 2, 'known': 3, 'length_m': None, 'verified': 4}
    ]


def _passes_with_points(home, away):
    """Две передачи хозяев в первом тайме (точная и неточная) и одна гостей во втором, с точками и направлением."""
    pass_ = lambda **c: {'id': str(uuid4()), 'kind': 'pass', 'side': 'home', 'player_id': home[0], **c}
    return [
        pass_(
            start_ms=100000,
            success=True,
            recipient_id=home[1],
            start_xy=[10.0, 5.0],
            end_xy=[13.0, 9.0],
            attacking_direction='right',
        ),
        pass_(start_ms=200000, success=False, start_xy=[20.0, 5.0], end_xy=[30.0, 5.0]),
        pass_(start_ms=300000, success=True),  # без точек: только в сводке
        pass_(
            side='away', player_id=away[0], start_ms=1500000, success=True, start_xy=[30.0, 10.0], end_xy=[24.0, 10.0]
        ),
    ]


def test_passes_carry_points_length_period_and_player_summary(admin_client, analytics_match, send_command):
    match, _, _, actions = _setup(
        admin_client, analytics_match, send_command, _passes_with_points, {'passes': [{'status': 'complete'}]}
    )
    home = [p['player_id'] for p in match['lineup'] if p['side'] == 'home']
    away = [p['player_id'] for p in match['lineup'] if p['side'] == 'away']
    stats = admin_client.get(f'/api/v1/matches/{match["id"]}/action-stats').json()
    points = {(p['side'], p['start_ms']): p for p in stats['passes']}
    assert set(points) == {('home', 100000), ('home', 200000), ('away', 1500000)}
    first = points[('home', 100000)]
    assert (first['player_id'], first['recipient_id'], first['length_m'], first['period']) == (
        home[0],
        home[1],
        5.0,
        '1',
    )
    assert first['start_xy'] == [10.0, 5.0] and first['end_xy'] == [13.0, 9.0]
    assert first['attacking_direction'] == 'right' and first['source'] == 'manual' and first['success'] is True
    assert all(p['verified'] for p in stats['passes'])  # внесены человеком
    assert points[('home', 200000)]['success'] is False and points[('home', 200000)]['attacking_direction'] == 'unknown'
    assert points[('away', 1500000)]['period'] == '2' and points[('away', 1500000)]['length_m'] == 6.0
    assert stats['pass_players'] == [  # хозяева первыми, затем по числу передач
        {'side': 'home', 'player_id': home[0], 'total': 3, 'accurate': 2, 'known': 3, 'length_m': 7.5, 'verified': 3},
        {'side': 'away', 'player_id': away[0], 'total': 1, 'accurate': 1, 'known': 1, 'length_m': 6.0, 'verified': 1},
    ]
    second = admin_client.get(f'/api/v1/matches/{match["id"]}/action-stats', params={'period': '2'}).json()
    assert [p['side'] for p in second['passes']] == ['away'] and len(second['pass_players']) == 1


def test_period_filter_and_invalid_period(admin_client, analytics_match, send_command):
    match, _, _, _ = _setup(admin_client, analytics_match, send_command, _actions, {'shots': [{'status': 'complete'}]})
    first = admin_client.get(f'/api/v1/matches/{match["id"]}/action-stats', params={'period': '1'}).json()
    second = admin_client.get(f'/api/v1/matches/{match["id"]}/action-stats', params={'period': '2'}).json()
    assert _row(first, 'shots_total')['home']['value'] == 3 and _row(second, 'shots_total')['home']['value'] == 1
    assert _row(second, 'duels_won')['away']['value'] == 100.0 and all(r['key'] != 'duels_won' for r in first['rows'])
    assert admin_client.get(f'/api/v1/matches/{match["id"]}/action-stats', params={'period': '7'}).status_code == 422
    assert admin_client.get(f'/api/v1/matches/{match["id"]}/action-stats', params={'period': 'x'}).status_code == 422


def test_guest_sees_only_published_action_version(admin_client, analytics_match, send_command):
    match, protocol, part, actions = _setup(
        admin_client, analytics_match, send_command, _actions, {'shots': [{'status': 'complete'}]}
    )
    path = f'/api/v1/public/matches/{match["id"]}/action-stats'
    assert admin_client.get(path).status_code == 404
    match = send_command(match, 'publish', {'version_id': protocol['id']}).json()
    assert publish_sources(admin_client, match, part, actions).status_code == 200
    admin_client.headers.pop('X-CSRF-Token', None)
    admin_client.cookies.clear()
    public = admin_client.get(path)
    assert public.status_code == 200, public.text
    assert public.json()['source']['published'] is True and _row(public.json(), 'shots_total')['home']['value'] == 4
    assert admin_client.get(f'/api/v1/matches/{match["id"]}/action-stats').status_code in (401, 403)


def test_ordinary_admin_cannot_read_private_stats(admin_client, analytics_match):
    grant(admin_client, False)
    assert admin_client.get(f'/api/v1/matches/{analytics_match["id"]}/action-stats').status_code == 403


def _cv_run_with_passes(client, match, *, side_map=None, publish=True, report=None, manifest=None):
    """Импорт пакета версии 3 (две передачи команды A: точная и неточная), подтверждение и публикация."""
    from uuid import uuid4

    from test_analysis_exchange import events_doc, result_zip

    from .test_analysis_assignments import command
    from .test_analysis_import import upload
    from .test_analysis_jobs import new_job

    side_map = side_map or {'A': 'home', 'B': 'away'}
    job = new_job(client, match)
    run = upload(
        client,
        match,
        result_zip(
            job,
            mutate=lambda m, r, t, c: (m.update(contract_version='3'), report and report(r), manifest and manifest(m)),
            extras={'events.json': events_doc()},
        ),
    )
    assert run.status_code == 200, run.text
    run = run.json()
    assert run['has_events'] is True
    saved = client.put(
        f'/api/v1/matches/{match["id"]}/analysis/runs/{run["id"]}/assignments',
        json={
            'request_id': str(uuid4()),
            'expected_revision': run['revision'],
            'side_map': side_map,
            'assignments': [
                {
                    'track_id': t['track_id'],
                    'player_id': next(
                        p['player_id'] for p in run['context']['rosters'] if p['side'] == side_map[t['team']]
                    ),
                }
                for t in run['tracks']
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    run = command(client, match, saved.json(), 'confirm')
    assert run.status_code == 200, run.text
    run = run.json()
    if publish:
        run = command(client, match, run, 'publish')
        assert run.status_code == 200, run.text
        run = run.json()
    return run


def test_auto_passes_from_published_video_analysis(admin_client, analytics_match):
    path = f'/api/v1/public/matches/{analytics_match["id"]}/action-stats'
    run = _cv_run_with_passes(admin_client, analytics_match, publish=False)
    private = admin_client.get(f'/api/v1/matches/{analytics_match["id"]}/action-stats')
    assert private.status_code == 200, private.text
    stats = private.json()
    assert stats['source']['kind'] == 'cv_auto' and stats['source']['run_published'] is False
    assert [r['key'] for r in stats['rows']] == ['passes_total', 'passes_accurate'] and {
        r['source'] for r in stats['rows']
    } == {'cv_auto'}
    accurate = _row(stats, 'passes_accurate')['home']
    assert (accurate['numerator'], accurate['denominator'], accurate['value']) == (1, 2, 50.0)
    assert _row(stats, 'passes_total')['away']['value'] == 0 and _row(stats, 'passes_total')['coverage'] == 'partial'
    assert stats['shots'] == [] and [p['key'] for p in stats['periods']] == ['all']
    # Передачи для карты: игрок — по назначенному фрагменту, адресат только у точной и не сам исполнитель.
    assert [(p['success'], p['length_m'], p['start_xy'], p['end_xy'], p['source']) for p in stats['passes']] == [
        (True, 8.1, [10.0, 5.0], [18.0, 6.0], 'cv_auto'),
        (False, 8.1, [10.0, 5.0], [18.0, 6.0], 'cv_auto'),
    ]
    assert all(p['side'] == 'home' and p['period'] is None and p['player_id'] for p in stats['passes'])
    assert not any(p['verified'] for p in stats['passes'])
    # Мяч найден своей моделью мяча, а не детектором игроков: к точности относится замеренная погрешность.
    assert stats['video_ball'] == 'ball_model'
    assert stats['passes'][1]['recipient_id'] is None and stats['passes'][0]['start_ms'] == 10000
    assert stats['pass_players'] == [
        {
            'side': 'home',
            'player_id': stats['passes'][0]['player_id'],
            'total': 2,
            'accurate': 1,
            'known': 2,
            'length_m': 8.1,
            'verified': 0,  # передачи из видео без проверки
        }
    ]
    assert admin_client.get(path).status_code == 404
    from .test_analysis_assignments import command

    assert command(admin_client, analytics_match, run, 'publish').status_code == 200
    admin_client.headers.pop('X-CSRF-Token', None)
    admin_client.cookies.clear()
    public = admin_client.get(path)
    assert public.status_code == 200, public.text
    assert public.json()['source']['published'] is True and _row(public.json(), 'passes_total')['home']['value'] == 2
    assert public.json()['passes'] == stats['passes'] and public.json()['pass_players'] == stats['pass_players']
    # Тайма нет в видеоанализе — пустая сводка: периоды странице задаёт протокол
    first = admin_client.get(path, params={'period': '1'})
    assert first.status_code == 200 and first.json()['rows'] == []


def test_auto_passes_follow_the_side_map(admin_client, analytics_match):
    _cv_run_with_passes(admin_client, analytics_match, side_map={'A': 'away', 'B': 'home'})
    stats = admin_client.get(f'/api/v1/matches/{analytics_match["id"]}/action-stats').json()
    assert _row(stats, 'passes_total')['away']['value'] == 2 and _row(stats, 'passes_total')['home']['value'] == 0
    away = {p['player_id'] for p in analytics_match['lineup'] if p['side'] == 'away'}
    assert {p['side'] for p in stats['passes']} == {'away'} and {p['player_id'] for p in stats['passes']} <= away


def test_passes_from_the_general_detector_are_marked(admin_client, analytics_match):
    """Запись трансляции без своей модели мяча: мяч искал детектор игроков, его модель — в манифесте."""
    model = 'ball/best.pt'  # модель мяча в events_doc
    _cv_run_with_passes(
        admin_client, analytics_match, manifest=lambda m: m['processor'].update(model=model, ball_model=model)
    )
    stats = admin_client.get(f'/api/v1/matches/{analytics_match["id"]}/action-stats').json()
    assert stats['video_ball'] == 'general' and len(stats['passes']) == 2
    admin_client.headers.pop('X-CSRF-Token', None)
    admin_client.cookies.clear()
    public = admin_client.get(f'/api/v1/public/matches/{analytics_match["id"]}/action-stats')
    assert public.status_code == 200 and public.json()['video_ball'] == 'general'


def _shots_only(home, away):
    return [
        {
            'id': str(uuid4()),
            'kind': 'shot',
            'player_id': home[1],
            'side': 'home',
            'start_ms': 60000,
            'on_target': False,
            'outcome': 'off_target',
            'start_xy': [30.0, 8.0],
        }
    ]


def test_manual_passes_win_and_auto_fills_only_missing_categories(admin_client, analytics_match, send_command):
    match, _, _, _ = _setup(
        admin_client, analytics_match, send_command, _shots_only, {'shots': [{'status': 'complete'}]}
    )
    _cv_run_with_passes(admin_client, match)
    stats = admin_client.get(f'/api/v1/matches/{match["id"]}/action-stats').json()
    assert (
        stats['source']['kind'] == 'mixed'
        and stats['source']['action_version_id']
        and stats['source']['run_published'] is True
    )
    assert _row(stats, 'shots_total')['source'] == 'manual' and _row(stats, 'passes_total')['source'] == 'cv_auto'
    assert stats['coverage']['passes'] == 'partial' and stats['video_ball'] == 'ball_model'
    assert len(stats['passes']) == 2 and {p['source'] for p in stats['passes']} == {'cv_auto'}


def test_manual_passes_are_not_mixed_with_auto(admin_client, analytics_match, send_command):
    match, _, _, _ = _setup(
        admin_client,
        analytics_match,  # noqa: F401
        send_command,
        _actions,
        {'shots': [{'status': 'complete'}], 'passes': [{'status': 'complete'}]},
    )
    _cv_run_with_passes(admin_client, match)
    stats = admin_client.get(f'/api/v1/matches/{match["id"]}/action-stats').json()
    assert stats['source']['kind'] == 'manual' and {r['source'] for r in stats['rows']} == {'manual'}
    assert _row(stats, 'passes_total')['home']['value'] == 4
    assert stats['passes'] == [] and stats['pass_players'][0]['total'] == 4  # ручные передачи без точек


def _heat(pitch, *cells):
    grid = [[0.0] * int(pitch['width_m'] + 0.999) for _ in range(int(pitch['length_m'] + 0.999))]
    for x, y, seconds in cells:
        grid[x][y] += seconds
    return grid


def _positions_report(report):
    """Треки 1 и 2 (команда A) — у левых ворот, трек 3 (B) — справа; центры команд дают направление атаки."""
    pitch = report['pitch']
    period = report['periods'][0]
    cells = {1: [(4, 5, 30)], 2: [(10, 8, 60)], 3: [(30, 12, 40)]}
    for player in period['players']:
        player['heatmap_s'] = _heat(pitch, *cells[player['track_id']])
    period['teams'] = {'A': {'heatmap_s': _heat(pitch, (8, 7, 90))}, 'B': {'heatmap_s': _heat(pitch, (30, 12, 40))}}


def test_video_positions_and_attack_direction_for_the_pass_network(admin_client, analytics_match):
    _cv_run_with_passes(admin_client, analytics_match, report=_positions_report)
    stats = admin_client.get(f'/api/v1/matches/{analytics_match["id"]}/action-stats').json()
    # Хозяева (A) у левых ворот: атакуют вправо, у передач направление из видео.
    assert stats['positions_orientation'] == 'attack'
    assert {p['attacking_direction'] for p in stats['passes']} == {'right'}
    home = next(p for p in stats['positions'] if p['side'] == 'home')
    away = next(p for p in stats['positions'] if p['side'] == 'away')
    # Оба трека команды A назначены одному игроку: средняя точка взвешена секундами.
    assert (home['x'], home['y'], home['observed_s']) == (8.5, 7.5, 90.0)
    assert (away['x'], away['y'], away['observed_s']) == (30.5, 12.5, 40.0)
    public = admin_client.get(f'/api/v1/public/matches/{analytics_match["id"]}/action-stats').json()
    assert public['positions'] == stats['positions']


def test_manual_actions_take_positions_from_the_published_video_analysis(admin_client, analytics_match, send_command):
    match, _, _, _ = _setup(
        admin_client, analytics_match, send_command, _passes_with_points, {'passes': [{'status': 'complete'}]}
    )
    before = admin_client.get(f'/api/v1/matches/{match["id"]}/action-stats').json()
    assert before['positions'] == [] and before['positions_orientation'] is None
    _cv_run_with_passes(admin_client, match, report=_positions_report)
    stats = admin_client.get(f'/api/v1/matches/{match["id"]}/action-stats').json()
    assert stats['source']['kind'] == 'manual' and len(stats['positions']) == 2
