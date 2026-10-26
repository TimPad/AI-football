"""Продвижение: кто играет в паре, кто прошёл дальше и что этап отдаёт следующему — всё вычисляется из результатов."""
from dataclasses import dataclass, field
from itertools import permutations
from aifootball.service.stages.rules.standings import rank, rank_across, Result, DEFAULT_CRITERIA


@dataclass(frozen=True)
class Leg:
    home: str
    away: str
    home_goals: int
    away_goals: int
    home_pens: int | None = None
    away_pens: int | None = None
    points: tuple[int, int, int] = (3, 1, 0)


@dataclass
class Outcome:
    """Что этап отдаёт следующему: места в группах, лучшие по месту, итоговые места."""
    places: dict = field(default_factory=dict)       # (group_no, place) -> team
    best: dict = field(default_factory=dict)         # (place, rank) -> team
    group_of: dict = field(default_factory=dict)     # team -> group_no
    final: dict = field(default_factory=dict)        # place -> team
    complete: bool = False


def pair_winner(teams, legs, expected_legs):
    """Победитель пары по сумме матчей; при равенстве — серия пенальти последнего матча; None — не определён."""
    if len(legs) < expected_legs: return None
    goals = {t: 0 for t in teams}
    for leg in legs:
        goals[leg.home] += leg.home_goals; goals[leg.away] += leg.away_goals
    a, b = teams
    if goals[a] != goals[b]: return a if goals[a] > goals[b] else b
    last = legs[-1]
    if last.home_pens is None or last.away_pens is None or last.home_pens == last.away_pens: return None
    return last.home if last.home_pens > last.away_pens else last.away


@dataclass
class PairState:
    key: str
    home: str | None
    away: str | None
    winner: str | None = None
    loser: str | None = None
    legs: list = field(default_factory=list)


def resolve_source(source, pairs, prior):
    if source is None: return None
    if 'entry' in source: return source['entry']
    if 'winner' in source:
        pair = pairs.get(source['winner']); return pair.winner if pair else None
    if 'loser' in source:
        pair = pairs.get(source['loser']); return pair.loser if pair else None
    if prior is None: return None
    if 'group' in source: return prior.places.get((source['group'], source['place']))
    if 'best' in source: return prior.best.get((source['best'], source['rank']))
    if 'stage_place' in source: return prior.final.get(source['stage_place'])
    return None


def resolve_bracket(fixtures, legs_by_key, prior=None):
    """fixtures — пары этапа (ключ, источники, bye, номер матча). legs_by_key[key] — сыгранные матчи пары по порядку.
    Пары обходятся в порядке раундов, поэтому источники «победитель/проигравший» уже вычислены."""
    prior = _separate_best(fixtures, prior)
    pairs = {}
    by_key = {}
    for f in fixtures: by_key.setdefault(f.key, []).append(f)
    order = sorted(by_key, key=lambda k: (_stage_order(by_key[k][0]), k))
    for key in order:
        group = sorted(by_key[key], key=lambda f: f.leg)
        main = group[-1]  # последний матч пары хранит стороны в порядке посева
        home = resolve_source(main.home, pairs, prior); away = resolve_source(main.away, pairs, prior)
        state = PairState(key, home, away)
        if main.bye:
            state.winner = home
        elif home and away:
            legs = [l for l in legs_by_key.get(key, []) if {l.home, l.away} == {home, away}]
            state.legs = legs
            state.winner = pair_winner((home, away), legs, len(group))
            if state.winner: state.loser = away if state.winner == home else home
        pairs[key] = state
    if 'F2' in pairs and pairs.get('F') and pairs['F'].winner and pairs['F'].winner == pairs['F'].home:
        # Переигровка не нужна: финал выиграла команда из верхней сетки.
        pairs['F2'] = PairState('F2', None, None)
    return pairs


def _stage_order(f):
    # Чётный раунд нижней сетки ждёт проигравших верхнего раунда r/2+1, нечётный — свой предыдущий; финалы — в конце.
    if f.bracket == 'lower': return f.round_no // 2 + 1 + (0.5 if f.round_no % 2 == 0 else 0.75)
    return f.round_no + {'third': 0.5, 'final': 1000, 'final_reset': 1001}.get(f.bracket, 0)


def _separate_best(fixtures, prior):
    """Лучшие команды одного места меняются местами между собой, чтобы не играть с победителем своей группы."""
    if prior is None or not prior.best: return prior
    first = [f for f in fixtures if f.round_no == 1 and f.bracket in (None, 'upper') and not f.bye]
    slots = sorted({(s['best'], s['rank']) for f in first for s in (f.home, f.away) if s and 'best' in s})
    teams = [prior.best.get(slot) for slot in slots]
    if not slots or None in teams: return prior
    def conflicts(assign):
        mapping = dict(zip(slots, assign)); total = 0
        for f in first:
            sides = [mapping.get((s['best'], s['rank'])) if s and 'best' in s else s for s in (f.home, f.away)]
            groups = [prior.group_of.get(x) if isinstance(x, str) else x.get('group') if isinstance(x, dict) else None for x in sides]
            if groups[0] is not None and groups[0] == groups[1]: total += 1
        return total
    choice = min(permutations(teams), key=conflicts) if len(teams) <= 8 else teams
    best = dict(prior.best); best.update(zip(slots, choice))
    return Outcome(prior.places, best, prior.group_of, prior.final, prior.complete)


def group_outcome(groups, results, criteria=DEFAULT_CRITERIA, lots=None, per_group=0, best=(), expected=None):
    """groups — составы групп; results[g] — результаты группы; expected[g] — число пар группы.
    Возвращает (таблицы, Outcome). Места группы известны, когда сыграны все её пары и нет равенства без жребия."""
    lots = lots or {}; tables = []; outcome = Outcome()
    for g, teams in enumerate(groups, 1):
        rows = rank(teams, results.get(g, []), criteria, lots.get(g, ()))
        tables.append(rows)
        done = expected is None or len(results.get(g, [])) >= expected[g - 1]
        for row in rows:
            outcome.group_of[row.team] = g
            if done and not row.tied: outcome.places[(g, row.place)] = row.team
    all_done = all(expected is None or len(results.get(g, [])) >= expected[g - 1] for g in range(1, len(groups) + 1))
    for item in best:
        candidates = [r for rows in tables for r in rows if r.place == item['place'] and not r.tied]
        ordered, cutoff_tied = rank_across(candidates, lots.get(f"best-{item['place']}", ()))
        if all_done and len(candidates) == len(groups) and not cutoff_tied(item['count']):
            for i, row in enumerate(ordered[:item['count']], 1): outcome.best[(item['place'], i)] = row.team
    outcome.complete = all_done
    if all_done and len(groups) == 1:
        outcome.final = {row.place: row.team for row in tables[0] if not row.tied}
    return tables, outcome
