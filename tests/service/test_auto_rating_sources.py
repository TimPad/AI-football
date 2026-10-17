"""Этап E: подтверждённый видеоанализ сам даёт версии участия и действий для оценок."""
from uuid import uuid4
from .test_analysis_jobs import analytics_match, new_job
from .test_analysis_assignments import command
from .test_analysis_import import upload
from .test_ratings_snapshots import base, calculate, publish_sources, revision
from aifootball.service.ratings.auto import presence


def _track(*spans):
    return {'intervals': [list(s) for s in spans]}


def test_presence_bridges_tracker_breaks_but_not_substitutions_or_a_sixth_player():
    tracks = {1: _track((0, 40)), 2: _track((45, 90)), 3: _track((150, 200))}
    # 5 с разрыва — обрыв трекера; 60 с — игрок уходил.
    assert presence(tracks, {1: 'p', 2: 'p', 3: 'p'}, {'p': 'home'}, 300000, 5) == {'p': [[0, 90000], [150000, 200000]]}
    # Пока игрок «пропал», на площадке уже пятеро других — разрыв не время на площадке.
    others = {10 + i: _track((0, 300)) for i in range(4)}
    tracks = {1: _track((0, 40)), 2: _track((45, 90)), 9: _track((40.5, 44.5)), **others}
    sides = {'p': 'home', 'q': 'home', **{f'o{i}': 'home' for i in range(4)}}
    people = presence(tracks, {1: 'p', 2: 'p', 9: 'q', **{10 + i: f'o{i}' for i in range(4)}}, sides, 300000, 5)
    assert people['p'] == [[0, 40000], [45000, 90000]] and people['q'] == [[40500, 44500]]


def test_presence_drops_the_handoff_duplicate_instead_of_six_on_pitch():
    others = {10 + i: _track((0, 100)) for i in range(4)}
    # Замена: уходящий виден до 50.8 с, вышедший — с 50.0 с.
    tracks = {1: _track((0, 50.8)), 2: _track((50, 100)), **others}
    sides = {'out': 'home', 'in': 'home', **{f'o{i}': 'home' for i in range(4)}}
    people = presence(tracks, {1: 'out', 2: 'in', **{10 + i: f'o{i}' for i in range(4)}}, sides, 100000, 5)
    on_pitch = lambda t: sum(any(a <= t < b for a, b in spans) for spans in people.values())
    assert max(on_pitch(t) for t in range(0, 100000, 100)) == 5
    assert people['out'][0][0] == 0 and people['in'][-1][1] == 100000


def _protocol(client, match, send, publish=False):
    for kind, payload in [('set_completeness', {'goals': 'complete', 'assists': 'complete', 'fouls': 'complete', 'cards': 'complete'}),
                          ('set_status', {'status': 'ended'}), ('confirm', {'acknowledge_incomplete': True})]:
        response = send(match, kind, payload); assert response.status_code == 200, response.text; match = response.json()
    protocol = client.get(f"/api/v1/matches/{match['id']}/versions").json()['items'][0]
    if publish:
        response = send(match, 'publish', {'version_id': protocol['id']}); assert response.status_code == 200, response.text
        match = response.json()
    return match, protocol


def _video(client, match, *, publish=False):
    """Пакет версии 3: трек 1 (A, 0–60 с) и 2 (A, 120–240 с) — разные игроки хозяев, трек 3 — гость.
    Две передачи трека 1: точная треку 2 и неточная."""
    from test_analysis_exchange import result_zip, events_doc
    job = new_job(client, match)
    run = upload(client, match, result_zip(job, mutate=lambda m, r, t, c: m.update(contract_version='3'), extras={'events.json': events_doc()}))
    assert run.status_code == 200, run.text; run = run.json()
    roster = run['context']['rosters']
    home = [p['player_id'] for p in roster if p['side'] == 'home']; away = [p['player_id'] for p in roster if p['side'] == 'away']
    players = {1: home[0], 2: home[1], 3: away[0]}
    saved = client.put(f"/api/v1/matches/{match['id']}/analysis/runs/{run['id']}/assignments", json={'request_id': str(uuid4()),
        'expected_revision': run['revision'], 'side_map': {'A': 'home', 'B': 'away'},
        'assignments': [{'track_id': tid, 'player_id': pid} for tid, pid in players.items()]})
    assert saved.status_code == 200, saved.text
    run = command(client, match, saved.json(), 'confirm'); assert run.status_code == 200, run.text; run = run.json()
    if publish:
        run = command(client, match, run, 'publish'); assert run.status_code == 200, run.text; run = run.json()
    return run, players


def test_confirming_video_creates_participation_and_passes_for_ratings(admin_client, analytics_match, send_command):
    match, protocol = _protocol(admin_client, analytics_match, send_command)
    run, players = _video(admin_client, match)
    auto = run['auto_sources']
    assert (auto['participation_revision'], auto['action_revision'], auto['players'], auto['passes'], auto['note']) == (1, 1, 3, 2, None)
    part = admin_client.get(f"/api/v1/matches/{match['id']}/participation").json()['current']
    assert part['auto'] is True and part['provenance']['source_kind'] == 'cv_auto'
    doc = part['document']
    assert (doc['clock_basis'], doc['time_basis'], doc['analysis_scope'], doc['duration_ms']) == ('video', 'running_clock', 'full_match', 240000)
    assert doc['source_analysis_run_id'] == run['id'] and doc['source_protocol_version_id'] == protocol['id']
    presence = {p['player_id']: p['presence'] for p in doc['players']}
    assert presence[players[1]] == [[0, 60000]] and presence[players[2]] == [[120000, 240000]]
    # Игрок без назначенного фрагмента — участие неизвестно, а не «не играл».
    unknown = [p for p in doc['players'] if p['player_id'] not in players.values()]
    assert unknown and all(p['presence'] is None and p['completeness'] == 'unknown' and p['appeared'] is None for p in unknown)
    actions = admin_client.get(f"/api/v1/matches/{match['id']}/performance-actions").json()['current']
    assert actions['auto'] is True and actions['document']['source_participation_version_id'] == part['id']
    passes = [a for a in actions['document']['actions'] if a['kind'] == 'pass']
    assert [(a['player_id'], a['recipient_id'], a['success'], a['start_ms']) for a in passes] == [
        (players[1], players[2], True, 10000), (players[1], None, False, 30000)]
    assert actions['document']['completeness'] == {'passes': [{'status': 'partial', 'intervals': [[0, 240000]], 'player_ids': None}]}
    record = next(a for a in actions['canonical_actions'] if a['kind'] == 'pass')
    assert record['source_kind'] == 'cv_auto' and record['source_refs'][0]['kind'] == 'cv_auto'
    # Командная сводка по-прежнему из событий прогона, без удвоения передач.
    stats = admin_client.get(f"/api/v1/matches/{match['id']}/action-stats").json()
    assert stats['source']['kind'] == 'cv_auto' and next(r for r in stats['rows'] if r['key'] == 'passes_total')['home']['value'] == 2


def test_ratings_use_video_minutes_with_presence_time_basis(admin_client, analytics_match, send_command):
    match, _ = _protocol(admin_client, analytics_match, send_command)
    _, players = _video(admin_client, match)
    effective = calculate(admin_client, match); assert effective.status_code == 200, effective.text
    history = lambda snapshot: admin_client.get(f"/api/v1/players/{players[1]}/ratings",
                                                params={'tournament_id': match['tournament_id'], 'snapshot_id': snapshot})
    rows = history(effective.json()['snapshot_id']); assert rows.status_code == 200, rows.text
    assert all(m['eligible_play_minutes'] is None for m in rows.json()['matches'])
    running = calculate(admin_client, match, time_basis='running_clock'); assert running.status_code == 200, running.text
    played = history(running.json()['snapshot_id']).json()['matches'][0]
    assert played['eligible_play_minutes'] == 1.0 and played['source'] == 'cv_auto'
    assert played['explanation']['source_note'].startswith('По автоматическим данным видео')
    # Неполная категория передач не превращается в ноль и не считается точностью.
    assert played['facts']['pass_completion_pct']['reason'] == 'incomplete_category'
    assert played['facts']['pass_completion_unresolved_count']['value'] == 0


def test_manual_versions_win_over_automatic_ones(admin_client, analytics_match, send_command):
    match, protocol = _protocol(admin_client, analytics_match, send_command)
    _video(admin_client, match)
    doc = {'clock_basis': 'game', 'time_basis': 'reviewed_effective', 'analysis_scope': 'full_match', 'duration_ms': 2400000,
           'source_protocol_version_id': protocol['id'], 'initial_five': {'home': [], 'away': []}, 'play_intervals': [[0, 2400000]],
           'players': []}
    current = admin_client.get(f"/api/v1/matches/{match['id']}/participation").json()
    manual = admin_client.put(f"/api/v1/matches/{match['id']}/participation", json={'request_id': str(uuid4()),
        'expected_revision': current['revision'], 'expected_match_revision': current['match_revision'], 'status': 'confirmed', 'document': doc})
    assert manual.status_code == 200, manual.text
    assert manual.json()['auto'] is False
    sources = admin_client.get(base(match) + '/analytics').json()['sources']
    source = next(s for s in sources if s['match_id'] == match['id'])
    assert source['participation_id'] == manual.json()['id'] and source['auto'] is False
    assert source['time_basis'] == 'reviewed_effective'
    overview = admin_client.get(f"/api/v1/matches/{match['id']}/participation").json()
    assert [v['auto'] for v in overview['versions']] == [False, True]


def test_published_video_becomes_the_public_rating_source_unless_chosen_manually(admin_client, analytics_match, send_command):
    match, protocol = _protocol(admin_client, analytics_match, send_command, publish=True)
    assert calculate(admin_client, match).status_code == 200  # рейтинг уже считали — его страницы должны устареть
    before = revision(admin_client, match)
    run, _ = _video(admin_client, match, publish=True)
    assert run['auto_sources']['note'] is None
    saved = admin_client.get(f"/api/v1/matches/{match['id']}/performance-publication").json()
    assert saved['participation_version_id'] == str(run['auto_sources']['participation_version_id'])
    assert saved['action_version_id'] == str(run['auto_sources']['action_version_id'])
    assert revision(admin_client, match) == before + 1
    # Ручной выбор администратора повторная публикация видео не трогает.
    match = admin_client.get(f"/api/v1/matches/{match['id']}").json()
    doc = {'clock_basis': 'game', 'time_basis': 'reviewed_effective', 'analysis_scope': 'full_match', 'duration_ms': 2400000,
           'source_protocol_version_id': protocol['id'], 'initial_five': {'home': [], 'away': []}, 'play_intervals': [[0, 2400000]], 'players': []}
    current = admin_client.get(f"/api/v1/matches/{match['id']}/participation").json()
    part = admin_client.put(f"/api/v1/matches/{match['id']}/participation", json={'request_id': str(uuid4()),
        'expected_revision': current['revision'], 'expected_match_revision': match['revision'], 'status': 'confirmed', 'document': doc}).json()
    adoc = {'clock_basis': 'game', 'analysis_scope': 'full_match', 'duration_ms': 2400000, 'source_participation_version_id': part['id'], 'actions': []}
    current = admin_client.get(f"/api/v1/matches/{match['id']}/performance-actions").json()
    actions = admin_client.put(f"/api/v1/matches/{match['id']}/performance-actions", json={'request_id': str(uuid4()),
        'expected_revision': current['revision'], 'expected_match_revision': match['revision'], 'status': 'confirmed', 'document': adoc}).json()
    assert publish_sources(admin_client, match, part, actions).status_code == 200
    review = command(admin_client, match, run, 'reviews'); assert review.status_code == 200, review.text
    again = command(admin_client, match, review.json(), 'confirm'); assert again.status_code == 200, again.text
    again = command(admin_client, match, again.json(), 'publish'); assert again.status_code == 200, again.text
    saved = admin_client.get(f"/api/v1/matches/{match['id']}/performance-publication").json()
    assert (saved['participation_version_id'], saved['action_version_id']) == (part['id'], actions['id'])


def test_unpublished_protocol_is_reported_and_not_published(admin_client, analytics_match, send_command):
    match, _ = _protocol(admin_client, analytics_match, send_command)
    run, _ = _video(admin_client, match, publish=True)
    assert run['auto_sources']['note'] == 'Протокол матча не опубликован'
    saved = admin_client.get(f"/api/v1/matches/{match['id']}/performance-publication").json()
    assert saved['participation_version_id'] is None and saved['action_version_id'] is None


def test_cabinet_ratings_follow_the_active_video_version(admin_client, analytics_match, send_command):
    match, _ = _protocol(admin_client, analytics_match, send_command)
    first, _ = _video(admin_client, match)
    review = command(admin_client, match, first, 'reviews'); assert review.status_code == 200, review.text
    second = command(admin_client, match, review.json(), 'confirm'); assert second.status_code == 200, second.text
    source = lambda: next(s for s in admin_client.get(base(match) + '/analytics').json()['sources'] if s['match_id'] == match['id'])
    assert source()['participation_id'] == str(second.json()['auto_sources']['participation_version_id'])
    # Администратор вернул активной первую версию — оценки берут её автоматические данные, а не последние по номеру.
    first = admin_client.get(f"/api/v1/matches/{match['id']}/analysis/runs/{first['id']}").json()
    assert command(admin_client, match, first, 'activate').status_code == 200
    assert source()['participation_id'] == str(first['auto_sources']['participation_version_id'])
    assert source()['action_id'] == str(first['auto_sources']['action_version_id'])
