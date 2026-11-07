import pytest
from pydantic import ValidationError
from aifootball.service.errors import DomainError
from aifootball.service.stages.schemas import StageConfig, template_stages
from aifootball.service.stages.generate import participants_placement, fixtures_for, scheme_for, qualifier_count


def test_config_validation():
    StageConfig.model_validate({'kind': 'groups', 'group_count': 4, 'advance': {'per_group': 2, 'best': []}})
    with pytest.raises(ValidationError): StageConfig.model_validate({'kind': 'groups'})
    with pytest.raises(ValidationError): StageConfig.model_validate({'kind': 'groups', 'group_count': 1})
    with pytest.raises(ValidationError): StageConfig.model_validate({'kind': 'round_robin', 'criteria': ['points', 'magic']})
    with pytest.raises(ValidationError): StageConfig.model_validate({'kind': 'round_robin', 'criteria': ['goal_diff']})
    with pytest.raises(ValidationError): StageConfig.model_validate({'kind': 'round_robin', 'criteria': ['points', 'buchholz']})


def test_templates():
    stages = template_stages('groups_playoff', {'group_count': 2, 'per_group': 2, 'third_place': True, 'best_thirds': 2})
    assert [s['kind'] for s in stages] == ['groups', 'single_elim']
    assert stages[1]['config']['source'] == {'previous': True}
    assert stages[0]['config']['advance']['best'] == [{'place': 3, 'count': 2}]
    assert [s['kind'] for s in template_stages('league', {'playoff_teams': 4})] == ['round_robin', 'single_elim']
    assert template_stages('playoff', {})[0]['config']['source'] == {'entries': 'all'}
    assert template_stages('double_elim', {'grand_final_reset': True})[0]['config']['grand_final_reset']


def test_groups_fixtures_have_group_numbers():
    config = StageConfig(kind='groups', group_count=2, advance={'per_group': 2})
    placement = participants_placement(config, 'snake', list('ABCDEFGH'), 0)
    specs = fixtures_for(config, placement)
    assert {s.group_no for s in specs} == {1, 2} and len(specs) == 12
    with pytest.raises(DomainError): participants_placement(config, 'seeded', list('ABCDEFGH'), 0)
    with pytest.raises(DomainError): participants_placement(config, 'pots', list('ABC'), 0)


def test_swiss_first_round_top_half_vs_bottom():
    specs = fixtures_for(StageConfig(kind='swiss', rounds=3), list('ABCDE'))
    assert [(s.home, s.away, s.bye) for s in specs] == [
        ({'entry': 'A'}, {'entry': 'C'}, False), ({'entry': 'B'}, {'entry': 'D'}, False), ({'entry': 'E'}, None, True)]


def test_scheme_after_groups_and_league():
    groups = StageConfig(kind='groups', group_count=2, advance={'per_group': 2})
    playoff = StageConfig(kind='single_elim', source={'previous': True})
    assert scheme_for(playoff, groups)[:2] == [{'group': 1, 'place': 1}, {'group': 2, 'place': 1}]
    assert qualifier_count(groups) == 4
    league = StageConfig(kind='round_robin', playoff_teams=4)
    assert scheme_for(playoff, league) == [{'stage_place': n} for n in range(1, 5)]
