from uuid import uuid4

from .test_analysis_assignments import assignments, import_run, save_assignments
from .test_analysis_jobs import analytics_match, grant  # noqa: F401


def lineup_without(client, match, player_id):
    m = client.get(f'/api/v1/matches/{match["id"]}').json()
    players = [
        {'entry_player_id': p['entry_player_id'], 'side': p['side']} for p in m['lineup'] if p['player_id'] != player_id
    ]
    r = client.post(
        f'/api/v1/matches/{match["id"]}/commands',
        json={
            'request_id': str(uuid4()),
            'expected_revision': m['revision'],
            'kind': 'set_lineup',
            'payload': {'players': players},
        },
    )
    assert r.status_code == 200, r.text


def decisions(run):
    return sorted((a['track_id'], a['player_id'], a['excluded_reason']) for a in run['assignments'])


def test_new_version_takes_the_labelling_when_fragments_match(admin_client, analytics_match):
    old = import_run(admin_client, analytics_match)
    home = [p['player_id'] for p in old['context']['rosters'] if p['side'] == 'home']
    saved = save_assignments(admin_client, analytics_match, old, absent=[home[1]])
    assert saved.status_code == 200, saved.text
    new = import_run(admin_client, analytics_match)
    assert decisions(new) == decisions(saved.json())
    assert new['absent_players'] == [home[1]]
    assert new['side_map_verified'] is True
    assert 'Перенесено решений из прежней версии: 3' in new['checks']['warnings']


def test_decisions_about_players_out_of_the_lineup_stay_behind(admin_client, analytics_match):
    old = import_run(admin_client, analytics_match)
    assert save_assignments(admin_client, analytics_match, old).status_code == 200
    away = assignments(old)[2]['player_id']
    lineup_without(admin_client, analytics_match, away)
    new = import_run(admin_client, analytics_match)
    assert [a['track_id'] for a in new['assignments']] == [1, 2]
    assert 'Перенесено решений из прежней версии: 2; не перенесено (игрок не в составе): 1' in new['checks']['warnings']


def test_new_version_with_other_fragments_starts_empty(admin_client, analytics_match):
    old = import_run(admin_client, analytics_match)
    assert save_assignments(admin_client, analytics_match, old).status_code == 200

    def other(m, r, t, c):
        t['tracks'][1]['intervals'] = [[30, 150]]

    new = import_run(admin_client, analytics_match, other)
    assert new['assignments'] == []
    assert 'Фрагменты отличаются от прежней версии — разметка не перенесена' in new['checks']['warnings']


def test_a_new_review_copies_who_did_not_take_part(admin_client, analytics_match):
    from .test_analysis_assignments import command

    run = import_run(admin_client, analytics_match)
    home = [p['player_id'] for p in run['context']['rosters'] if p['side'] == 'home']
    run = save_assignments(admin_client, analytics_match, run, absent=[home[1]]).json()
    confirmed = command(admin_client, analytics_match, run, 'confirm').json()
    review = command(admin_client, analytics_match, confirmed, 'reviews').json()
    assert review['absent_players'] == [home[1]]
