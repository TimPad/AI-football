"""Жеребьёвка: корзины, змейка и схема выхода из групп в сетку."""
import random
from itertools import permutations
from aifootball.service.stages.rules.brackets import seed_positions, bracket_size


def group_sizes(count, groups):
    return [count // groups + (1 if g < count % groups else 0) for g in range(groups)]


def pots_draw(seeding, groups, seed):
    """Корзины по посеву; из каждой корзины в каждую группу случайно одна команда."""
    rng = random.Random(seed); result = [[] for _ in range(groups)]
    for start in range(0, len(seeding), groups):
        pot = list(seeding[start:start + groups]); rng.shuffle(pot)
        for g, team in enumerate(pot): result[g].append(team)
    return result


def snake_draw(seeding, groups):
    result = [[] for _ in range(groups)]
    for i, team in enumerate(seeding):
        row, col = divmod(i, groups)
        result[col if row % 2 == 0 else groups - 1 - col].append(team)
    return result


def random_order(seeding, seed):
    order = list(seeding); random.Random(seed).shuffle(order); return order


def meeting_round(size, a, b):
    """Раунд, в котором встречаются номера посева a и b, если оба побеждают."""
    places = {s: i for i, s in enumerate(seed_positions(size))}
    return (places[a] ^ places[b]).bit_length()


def group_scheme(group_count, per_group, best=()):
    """Источники по силе для сетки из групп: победители групп разнесены, одногруппники встречаются как можно позже."""
    tiers = [[{'group': g, 'place': p} for g in range(1, group_count + 1)] for p in range(1, per_group + 1)]
    for item in best:
        tiers.append([{'best': item['place'], 'rank': r} for r in range(1, item['count'] + 1)])
    size = bracket_size(sum(map(len, tiers))); rounds = size.bit_length() - 1
    def cost(seq):
        total = 0
        for i, a in enumerate(seq):
            for j in range(i + 1, len(seq)):
                if 'group' in a and a.get('group') == seq[j].get('group'):
                    total += 4 ** (rounds - meeting_round(size, i + 1, j + 1))
        return total
    placed = list(tiers[0])
    for tier in tiers[1:]:
        options = permutations(tier) if len(tier) <= 8 else [tier]
        placed += min(options, key=lambda perm: cost(placed + list(perm)))
    return placed
