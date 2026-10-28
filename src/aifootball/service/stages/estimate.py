"""Подсказки при выборе формата: матчи, игровые дни, предупреждения и рекомендация — теми же генераторами пар."""
import random
from math import ceil
from aifootball.service.stages.schemas import template_stages, StageConfig, ELIMINATION
from aifootball.service.stages.generate import fixtures_for, scheme_for, qualifier_count
from aifootball.service.stages.rules.brackets import bracket_size
from aifootball.service.stages.rules.draws import snake_draw, group_sizes
from aifootball.service.stages.rules.progress import Leg, resolve_bracket

TEMPLATES = ('league', 'groups_playoff', 'playoff', 'double_elim', 'swiss')


def auto_params(template, n):
    """Параметры по умолчанию: группы не меньше 4 команд, третьи места добирают плей-офф до степени двойки."""
    if template == 'groups_playoff':
        groups = max(2, n // 4)
        qualifiers = 2 * groups; missing = bracket_size(qualifiers) - qualifiers
        best = missing if missing <= groups and n - qualifiers >= missing else 0
        return {'group_count': groups, 'per_group': 2, 'best_thirds': best, 'legs': 1}
    if template == 'league': return {'legs': 1}
    if template == 'swiss': return {'rounds': swiss_rounds(n)}
    return {}


def swiss_rounds(n): return max(1, (n - 1).bit_length())


def fix_for(count):
    """Сколько групп поместится в состав: по 4 команды, но не меньше двух в группе."""
    return {'group_count': max(2, count // 4) if count >= 8 else max(1, count // 2)}


def _placement(config, prior, teams):
    if config.source.get('previous'): return scheme_for(config, prior)
    if config.kind == 'groups': return snake_draw(teams, config.group_count)
    if config.kind in ELIMINATION: return [{'entry': t} for t in teams]
    return teams


def _elimination_range(config, specs, teams, rng):
    """Матчей у команды в сетке: прогоны со случайными победителями; сетка из предыдущего этапа — от 1 до числа раундов."""
    real = [s for s in specs if not s.bye and s.bracket != 'final_reset']
    if config.source.get('previous'):
        return 1, len({s.round_no for s in real if s.bracket == 'upper'}) + (1 if config.third_place else 0)
    low, high = None, 0
    for _ in range(30):
        legs = {}
        for _ in range(64):
            pairs = resolve_bracket(specs, legs)
            todo = [p for p in pairs.values() if p.home and p.away and p.winner is None and p.key not in legs]
            if not todo: break
            for p in todo: legs[p.key] = [Leg(p.home, p.away, *rng.choice([(1, 0), (0, 1)]))]
        played = {t: 0 for t in teams}
        for key, items in legs.items():
            if key == 'F2': continue  # переигровку финала не считаем, как и в числе матчей
            for leg in items: played[leg.home] += 1; played[leg.away] += 1
        low = min(played.values()) if low is None else min(low, min(played.values()))
        high = max(high, max(played.values()))
    return low or 0, high


def _days(tours, per_day): return sum(ceil(k / per_day) if per_day else 1 for k in tours)


def estimate(template, params, n, days=None, per_day=None):
    merged = {**auto_params(template, n), **(params or {})}
    configs = [StageConfig.model_validate(s['config']) for s in template_stages(template, merged)]
    rng = random.Random(n); warnings = []; fix = None
    matches = 0; tours = []; low = high = 0; prior = None; count = n
    for config in configs:
        teams = [f't{i}' for i in range(count)]
        if config.kind == 'groups':
            if config.group_count * 2 > count:
                fix = fix_for(count)
                warnings.append(f'Для {config.group_count} групп нужно минимум {config.group_count * 2} команд')
                config = config.model_copy(update={'group_count': max(1, fix['group_count'])})
            sizes = group_sizes(count, config.group_count)
            if len(set(sizes)) > 1:
                warnings.append(f"Группы {', '.join(map(str, sizes))}: третьи места сравниваются по очкам за матч")
            if sum(b.count for b in config.advance.best) > config.group_count:
                warnings.append('Лучших команд места больше, чем групп')
        if config.kind == 'swiss':
            rounds = config.rounds or swiss_rounds(count)
            matches += rounds * (count // 2); tours += [count // 2] * rounds
            low += rounds - (1 if count % 2 else 0); high += rounds
        else:
            specs = fixtures_for(config, _placement(config, prior, teams))
            real = [s for s in specs if not s.bye and s.bracket != 'final_reset']
            matches += len(real)
            by_round = {}
            for s in real:
                # Матч за 3-е место играется в день финала; каждый матч пары из двух — отдельный день.
                bracket = 'final' if s.bracket == 'third' else s.bracket
                round_no = s.round_no if s.bracket != 'third' else max(x.round_no for x in real if x.bracket == 'upper')
                by_round.setdefault((round_no, str(bracket), s.leg), []).append(s)
            tours += [len(v) for _, v in sorted(by_round.items())]
            if config.kind in ELIMINATION:
                byes = bracket_size(count) - count
                if byes and not config.source.get('previous'):
                    warnings.append(f'{byes} команд начнут со второго раунда (пропуск хода)')
                a, b = _elimination_range(config, specs, teams, rng)
            else:
                played = {}
                for s in real:
                    for side in (s.home, s.away): played[side['entry']] = played.get(side['entry'], 0) + 1
                a, b = min(played.values(), default=0), max(played.values(), default=0)
            low += a if prior is None else 0; high += b
        if config.kind in ('round_robin', 'swiss') and config.playoff_teams and config.playoff_teams > count:
            warnings.append(f'В плей-офф выходит {config.playoff_teams} команд, а играет {count}')
        prior = config
        nxt = qualifier_count(config) if config.kind == 'groups' or config.playoff_teams else count
        count = min(count, nxt or count)
    need = _days(tours, per_day)
    return {'template': template, 'params': merged, 'summary': summary(configs, n), 'matches': matches,
            'per_team': [low, high], 'rounds': len(tours), 'days': need,
            'fits': None if days is None else need <= days, 'warnings': warnings, 'fix': fix,
            'recommended': False, 'reason': None}


def _plural(n, one, few, many):
    tail = n % 100
    if 11 <= tail <= 14: return many
    return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


def summary(configs, n):
    first = configs[0]
    if first.kind == 'groups':
        groups = min(first.group_count, max(1, n // 2)); sizes = group_sizes(n, groups); lo, hi = min(sizes), max(sizes)
        q = first.advance.per_group * groups + sum(b.count for b in first.advance.best)
        word = _plural(groups, 'группа', 'группы', 'групп')
        return f"{groups} {word} по {lo if lo == hi else f'{lo}–{hi}'} команд, в плей-офф {q}"
    if first.kind == 'round_robin':
        tail = f', в плей-офф {first.playoff_teams}' if first.playoff_teams else ''
        return ('Два круга' if first.legs == 2 else 'Один круг') + tail
    if first.kind == 'swiss':
        rounds = first.rounds or swiss_rounds(n)
        tail = f', в плей-офф {first.playoff_teams}' if first.playoff_teams else ''
        return f"{rounds} {_plural(rounds, 'тур', 'тура', 'туров')}{tail}"
    return f'Сетка на {bracket_size(n)} мест'


def estimate_all(n, days=None, per_day=None, template=None, params=None):
    """Карточки пяти шаблонов и одна рекомендация по правилу из спецификации."""
    cards = [estimate(t, params if t == template else None, n, days, per_day) for t in TEMPLATES]
    by = {c['template']: c for c in cards}
    fits = lambda c: c['fits'] is not False
    if (days is not None and fits(by['league'])) or (days is None and n <= 6):
        choice = by['league']
    elif n >= 8 and fits(by['groups_playoff']) and not by['groups_playoff']['fix']:
        choice = by['groups_playoff']
    else:
        fitting = [c for c in cards if fits(c) and c['template'] in ('league', 'groups_playoff', 'playoff') and not c['fix']]
        if fitting:
            choice = max(fitting, key=lambda c: (c['per_team'][0], -c['matches']))
        else:
            choice = min(cards, key=lambda c: (c['days'], c['matches']))
            choice['warnings'].insert(0, f"Ни один формат не укладывается: нужно минимум {choice['days']} игровых дней")
    choice['recommended'] = True
    k = choice['per_team'][0]; d = choice['days']
    choice['reason'] = (f"Каждая команда сыграет минимум {k} {_plural(k, 'матч', 'матча', 'матчей')} "
                        f"за {d} {_plural(d, 'игровой день', 'игровых дня', 'игровых дней')}")
    return cards
