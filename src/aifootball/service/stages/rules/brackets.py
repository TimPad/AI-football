"""Пары круговых этапов и сеток на выбывание: чистые функции без базы."""
from dataclasses import dataclass, field, replace

# Источник стороны пары: {'entry': id}, {'winner': key}, {'loser': key},
# {'group': 'A', 'place': 1}, {'best': 3, 'rank': 1}, {'stage_place': 1}; None — соперника нет.
Source = dict | None


@dataclass(frozen=True)
class FixtureSpec:
    key: str
    round_no: int
    home: Source
    away: Source
    bracket: str | None = None
    slot: int = 0
    leg: int = 1
    group_no: int | None = None
    bye: bool = False


def entry(value):
    return None if value is None else {'entry': str(value)}


def berger_rounds(teams, legs=1):
    """Туры методом Бергера: последняя позиция неподвижна, остальные вращаются; отдых не создаёт пару."""
    items = list(teams)
    if len(items) % 2: items.append(None)
    n = len(items); rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = items[i], items[n - 1 - i]
            if (i == 0 and r % 2) or (i > 0 and i % 2): a, b = b, a
            if a is not None and b is not None: pairs.append((a, b))
        rounds.append(pairs)
        items = [items[n - 2], *items[:n - 2], items[n - 1]]
    if legs == 2: rounds += [[(b, a) for a, b in pairs] for pairs in rounds]
    return rounds


def round_robin(teams, legs=1, group_no=None):
    prefix = f'G{group_no}' if group_no is not None else 'L'
    return [FixtureSpec(f'{prefix}-R{r}-{i}', r, entry(a), entry(b), group_no=group_no, slot=i)
            for r, pairs in enumerate(berger_rounds(teams, legs), 1) for i, (a, b) in enumerate(pairs, 1)]


def seed_positions(size):
    """Номера посева по местам сетки: 1–16, 8–9… — первые номера встречаются как можно позже."""
    order = [1]
    while len(order) < size:
        total = len(order) * 2 + 1
        order = [s for seed in order for s in (seed, total - seed)]
    return order


def bracket_size(count):
    size = 1
    while size < count: size *= 2
    return size


def _legs(spec, two_leg):
    if not two_leg or spec.bye: return [spec]
    # В первом матче принимает нижняя сторона пары, во втором — сеянная выше.
    return [replace(spec, home=spec.away, away=spec.home, leg=1), replace(spec, leg=2)]


def single_elim(seeds, third_place=False, two_leg_rounds=()):
    """seeds — источники по силе (первый сильнейший). Ключи: U<раунд>-<пара>, T — за 3-е место."""
    size = bracket_size(len(seeds)); rounds = size.bit_length() - 1
    padded = list(seeds) + [None] * (size - len(seeds))
    places = [padded[s - 1] for s in seed_positions(size)]
    specs = []
    for r in range(1, rounds + 1):
        for slot in range(1, size // 2 ** r + 1):
            if r == 1: home, away = places[2 * slot - 2], places[2 * slot - 1]
            else: home, away = {'winner': f'U{r-1}-{2*slot-1}'}, {'winner': f'U{r-1}-{2*slot}'}
            specs.append(FixtureSpec(f'U{r}-{slot}', r, home, away, 'upper', slot))
    if third_place and rounds >= 2:
        specs.append(FixtureSpec('T', rounds, {'loser': f'U{rounds-1}-1'}, {'loser': f'U{rounds-1}-2'}, 'third', 1))
    specs = prune(specs)
    return [leg for spec in specs for leg in _legs(spec, spec.round_no in two_leg_rounds and spec.bracket != 'third')]


def double_elim(seeds, grand_final_reset=False):
    """Верхняя сетка как олимпийка; проигравшие опускаются в нижнюю (L<раунд>-<пара>), финал F и переигровка F2."""
    size = bracket_size(max(len(seeds), 4)); k = size.bit_length() - 1
    upper = [s for s in single_elim(seeds) if s.bracket == 'upper']
    specs = list(upper)
    # L1: проигравшие первого раунда верхней сетки между собой.
    for slot in range(1, size // 4 + 1):
        specs.append(FixtureSpec(f'L1-{slot}', 1, {'loser': f'U1-{2*slot-1}'}, {'loser': f'U1-{2*slot}'}, 'lower', slot))
    for j in range(1, k):
        count = size // 2 ** (j + 1)
        # Чётный раунд: победители нижней против проигравших верхней в обратном порядке — меньше повторных встреч.
        for slot in range(1, count + 1):
            specs.append(FixtureSpec(f'L{2*j}-{slot}', 2 * j, {'winner': f'L{2*j-1}-{slot}'},
                                     {'loser': f'U{j+1}-{count+1-slot}'}, 'lower', slot))
        if j < k - 1:
            for slot in range(1, count // 2 + 1):
                specs.append(FixtureSpec(f'L{2*j+1}-{slot}', 2 * j + 1, {'winner': f'L{2*j}-{2*slot-1}'},
                                         {'winner': f'L{2*j}-{2*slot}'}, 'lower', slot))
    specs.append(FixtureSpec('F', k + 1, {'winner': f'U{k}-1'}, {'winner': f'L{2*(k-1)}-1'}, 'final', 1))
    if grand_final_reset:
        # Пара показывается и назначается, только если финал выиграла команда из нижней сетки.
        specs.append(FixtureSpec('F2', k + 2, {'winner': f'L{2*(k-1)}-1'}, {'winner': f'U{k}-1'}, 'final_reset', 1))
    return prune(specs)


def prune(specs):
    """Пустые места сетки: пара с одним соперником — пропуск хода, без соперников — исчезает."""
    specs = list(specs)
    while True:
        by_key = {s.key: s for s in specs}
        def resolve(source):
            if not source or ('winner' not in source and 'loser' not in source): return source, False
            ref = by_key.get(source.get('winner') or source.get('loser'))
            if ref is None: return None, True
            if ref.bye:
                if 'loser' in source: return None, True
                return (ref.home or ref.away), True
            return source, False
        changed = False; result = []
        for s in specs:
            home, ch1 = resolve(s.home); away, ch2 = resolve(s.away); changed |= ch1 or ch2
            if home is None and away is None:
                changed = True; continue
            bye = home is None or away is None
            if bye and not s.bye: changed = True
            if bye: home, away = (home or away), None
            result.append(replace(s, home=home, away=away, bye=bye))
        if not changed: return result
        specs = result
