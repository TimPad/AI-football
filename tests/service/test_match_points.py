"""Публичный рейтинг матча по действиям: протокол, разметка по видео и передачи из видеоанализа."""

from uuid import uuid4

from .test_analysis_jobs import analytics_match, new_job  # noqa: F401
from .test_auto_rating_sources import _protocol
from .test_video_tagging import _run, _save, _tags


def _goal(send_command, match, **fields):
    goal = str(uuid4())
    event = {'id': goal, 'kind': 'goal', 'side': 'home', 'period': 1, 'elapsed_ms': 60000, **fields}
    added = send_command(match, 'add_event', {'event': event})
    assert added.status_code == 200, added.text
    return goal, added.json()


def _rating(client, match):
    response = client.get(f'/api/v1/public/matches/{match["id"]}/match-rating')
    assert response.status_code == 200, response.text
    return response.json()


def test_rating_waits_for_goal_authors_and_says_what_is_missing(admin_client, analytics_match, send_command):
    goal, match = _goal(send_command, analytics_match)
    match, _ = _protocol(admin_client, match, send_command, publish=True)
    _, home, away = _run(admin_client, match)
    actions, links = _tags(home, away, goal_id=goal)
    _save(admin_client, match, actions, links, complete=False)
    value = _rating(admin_client, match)
    assert value['ready'] is False and value['items'] == [] and value['best_player_id'] is None
    missing = value['missing']
    assert (missing['goals_total'], missing['goals_without_author']) == (1, 1)
    # Сейв без вратаря, блок и отбор без игрока; возврат в момент отбора — часть отбора.
    assert missing['actions_without_player'] == 3
    assert missing['goalkeeper_unknown'] == ['home', 'away']
    assert 'shots' in missing['partial_categories']
    assert value['policy']['points']['goal'] == 1.0


def test_rating_counts_goal_assist_tagged_shot_and_passes(admin_client, analytics_match, send_command):
    roster = admin_client.get(f'/api/v1/matches/{analytics_match["id"]}').json()['lineup']
    # Задание обработки упорядочивает состав по player_id (а состав матча — по порядку добавления): трек 1 у _run — home[0].
    home = sorted(p['player_id'] for p in roster if p['side'] == 'home')
    goal, match = _goal(send_command, analytics_match, player_id=home[0], assist_id=home[1], assist_known=True)
    match, _ = _protocol(admin_client, match, send_command, publish=True)
    _, run_home, away = _run(admin_client, match)
    assert run_home[:2] == home[:2]
    actions, links = _tags(home, away, goal_id=goal)
    _save(admin_client, match, actions, links)
    value = _rating(admin_client, match)
    assert value['ready'] is True
    items = {i['player_id']: i for i in value['items']}
    scorer = {p['key']: (p['count'], p['points']) for p in items[home[0]]['parts']}
    assert scorer['goal'] == (1, 1.0) and scorer['shot_on_target'] == (1, 0.15)
    assert {p['key']: (p['count'], p['points']) for p in items[home[1]]['parts']}['assist'] == (1, 0.6)
    for item in items.values():
        total = 6.0 + sum(p['points'] for p in item['parts'])
        assert item['rating'] == round(min(10.0, max(3.0, total)) + 1e-9, 1)
    assert value['best_player_id'] == home[0]
    assert value['missing']['goals_without_author'] == 0


def test_rating_needs_a_published_protocol(admin_client, analytics_match):
    response = admin_client.get(f'/api/v1/public/matches/{analytics_match["id"]}/match-rating')
    assert response.status_code == 404
