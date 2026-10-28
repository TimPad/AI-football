import pytest
from aifootball.service.stages.estimate import auto_params, estimate, estimate_all
from aifootball.service.stages.schemas import template_stages, StageConfig
from aifootball.service.stages.generate import fixtures_for, scheme_for, qualifier_count


def real_matches(template, params, n):
    """Число пар, которые реально создаст жеребьёвка этих параметров."""
    stages = [StageConfig.model_validate(s['config']) for s in template_stages(template, params)]
    teams = [f't{i}' for i in range(n)]; total = 0; prior = None
    for config in stages:
        if config.source.get('previous'):
            placement = scheme_for(config, prior)
        elif config.kind == 'groups':
            from aifootball.service.stages.rules.draws import snake_draw
            placement = snake_draw(teams, config.group_count)
        elif config.kind in ('single_elim', 'double_elim'):
            placement = [{'entry': t} for t in teams]
        else:
            placement = teams
        specs = [s for s in fixtures_for(config, placement) if not s.bye and s.bracket != 'final_reset']
        total += len(specs) if config.kind != 'swiss' else (config.rounds or (n - 1).bit_length()) * (n // 2)
        prior = config
    return total


@pytest.mark.parametrize('n', [4, 5, 6, 7, 8, 11, 14, 16, 20, 24])
@pytest.mark.parametrize('template', ['league', 'groups_playoff', 'playoff', 'double_elim', 'swiss'])
def test_matches_equal_real_fixtures(template, n):
    params = auto_params(template, n)
    assert estimate(template, params, n)['matches'] == real_matches(template, params, n)


def test_auto_groups_have_at_least_four_teams_and_power_of_two_playoff():
    p = auto_params('groups_playoff', 14)
    assert (p['group_count'], p['per_group'], p['best_thirds']) == (3, 2, 2)


def test_days_with_matches_per_day():
    league = estimate('league', auto_params('league', 6), 6)
    assert league['rounds'] == 5 and league['days'] == 5
    assert estimate('league', auto_params('league', 6), 6, per_day=2)['days'] == 10     # 3 матча тура → 2 дня


@pytest.mark.parametrize('n,days,expected', [(4, None, 'league'), (6, None, 'league'), (8, None, 'groups_playoff'),
                                             (14, 6, 'playoff'), (14, 8, 'groups_playoff'), (14, 20, 'league'), (20, 3, 'playoff')])
def test_recommendation_rule(n, days, expected):
    cards = estimate_all(n, days=days, per_day=8)
    assert [c['template'] for c in cards if c['recommended']] == [expected]


def test_nothing_fits_warns_with_minimum_days():
    cards = estimate_all(20, days=3, per_day=8)
    choice = next(c for c in cards if c['recommended'])
    assert choice['template'] == 'playoff' and choice['warnings'][0] == 'Ни один формат не укладывается: нужно минимум 5 игровых дней'
    assert choice['reason'] == 'Каждая команда сыграет минимум 1 матч за 5 игровых дней'


def test_warnings_and_fix():
    card = estimate('groups_playoff', {'group_count': 4, 'per_group': 2}, 7)
    assert card['fix'] == {'group_count': 3}
    assert any('минимум 8 команд' in w for w in card['warnings'])
    assert any('пропуск' in w.lower() or 'второго раунда' in w for w in estimate('playoff', {}, 6)['warnings'])


def test_estimate_endpoint(admin_client, tournament_factory):
    t = tournament_factory()
    assert admin_client.post(f"/api/v1/tournaments/{t['id']}/format/estimate", json={}).status_code == 422   # нет команд
    r = admin_client.post(f"/api/v1/tournaments/{t['id']}/format/estimate",
                          json={'teams': 14, 'days': 8, 'per_day': 8, 'template': 'groups_playoff', 'params': {'group_count': 3}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['teams'] == 14 and len(body['cards']) == 5
    card = next(c for c in body['cards'] if c['template'] == 'groups_playoff')
    assert card['recommended'] and card['summary'] == '3 группы по 4–5 команд, в плей-офф 8'
    assert admin_client.post(f"/api/v1/tournaments/{t['id']}/format/estimate", json={'teams': 8, 'params': {'x': 1}}).status_code == 422
