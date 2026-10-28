"""Пары этапа из настроек и результата жеребьёвки."""
from aifootball.service.errors import DomainError
from aifootball.service.stages.rules.brackets import FixtureSpec, round_robin, single_elim, double_elim, entry
from aifootball.service.stages.rules.draws import pots_draw, snake_draw, random_order, group_scheme
from aifootball.service.stages.schemas import ELIMINATION

METHODS = {'groups': ('pots', 'snake', 'manual'), 'round_robin': ('random', 'seeded', 'manual'),
           'swiss': ('seeded', 'random', 'manual'), 'single_elim': ('seeded', 'random', 'scheme', 'manual'),
           'double_elim': ('seeded', 'random', 'scheme', 'manual')}


def participants_placement(config, method, seeding, seed, placement=None):
    """Составы групп (списки заявок), порядок источников сетки или порядок команд круга."""
    if method not in METHODS[config.kind]: raise DomainError('validation', 'Этот способ жеребьёвки не подходит этапу')
    seeding = [str(item) for item in seeding]
    if method == 'manual': return placement
    if config.kind == 'groups':
        if len(seeding) < 2 * config.group_count:
            from aifootball.service.stages.estimate import fix_for
            raise DomainError('not_enough_teams', f'Для {config.group_count} групп нужно минимум {2 * config.group_count} команд',
                              fields={'group_count': str(fix_for(len(seeding))['group_count'])})
        return pots_draw(seeding, config.group_count, seed) if method == 'pots' else snake_draw(seeding, config.group_count)
    order = random_order(seeding, seed) if method == 'random' else seeding
    return [entry(team) for team in order] if config.kind in ELIMINATION else order


def fixtures_for(config, placement):
    if config.kind == 'groups':
        return [spec for g, members in enumerate(placement, 1) for spec in round_robin(members, config.legs, group_no=g)]
    if config.kind == 'round_robin': return round_robin(placement, config.legs)
    if config.kind == 'single_elim':
        return single_elim(placement, config.third_place, tuple(config.two_leg_rounds))
    if config.kind == 'double_elim': return double_elim(placement, config.grand_final_reset)
    return swiss_first_round(placement)


def swiss_first_round(order):
    """Первый тур швейцарки: верхняя половина посева против нижней, отдых — последнему при нечётном числе."""
    teams = list(order); bye = teams.pop() if len(teams) % 2 else None
    half = len(teams) // 2
    specs = [FixtureSpec(f'S1-{i}', 1, entry(teams[i - 1]), entry(teams[half + i - 1]), slot=i) for i in range(1, half + 1)]
    if bye is not None: specs.append(FixtureSpec(f'S1-{half + 1}', 1, entry(bye), None, slot=half + 1, bye=True))
    return specs


def scheme_for(config, prior):
    """Источники по силе для сетки после предыдущего этапа (prior — его StageConfig)."""
    if prior.kind == 'groups':
        return group_scheme(prior.group_count, prior.advance.per_group, [b.model_dump() for b in prior.advance.best])
    if not prior.playoff_teams: raise DomainError('validation', 'Укажите, сколько команд выходит в плей-офф')
    return [{'stage_place': n} for n in range(1, prior.playoff_teams + 1)]


def qualifier_count(prior):
    if prior.kind == 'groups':
        return prior.advance.per_group * prior.group_count + sum(b.count for b in prior.advance.best)
    return prior.playoff_teams or 0
