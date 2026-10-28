from collections import Counter
import random
import pytest
from aifootball.service.stages.rules.brackets import (berger_rounds, round_robin, seed_positions,
    single_elim, double_elim, entry, bracket_size, FixtureSpec)
from aifootball.service.stages.rules.draws import pots_draw, snake_draw, group_scheme, group_sizes, meeting_round
from aifootball.service.stages.rules.standings import rank, rank_across, Result as R, Row, SWISS_CRITERIA
from aifootball.service.stages.rules.swiss import swiss_pairs
from aifootball.service.stages.rules.progress import Leg, pair_winner, resolve_bracket, group_outcome



@pytest.mark.parametrize('n', range(2, 17))
def test_berger_every_pair_once_and_home_balance(n):
    rounds = berger_rounds(range(n))
    pairs = Counter(frozenset(p) for r in rounds for p in r)
    assert len(pairs) == n * (n - 1) // 2 and set(pairs.values()) == {1}
    home = Counter(a for r in rounds for a, _ in r); away = Counter(b for r in rounds for _, b in r)
    assert max(abs(home[t] - away[t]) for t in range(n)) <= (0 if n % 2 else 1)
    assert all(len({t for p in r for t in p}) == 2 * len(r) for r in rounds)  # никто не играет дважды за тур


def test_second_leg_mirrors_home():
    first, second = berger_rounds('ABCD'), berger_rounds('ABCD', legs=2)[3:]
    assert second == [[(b, a) for a, b in r] for r in first]


def test_seed_positions_standard():
    assert seed_positions(8) == [1, 8, 4, 5, 2, 7, 3, 6]


def simulate(specs, rng):
    win, lose, losses = {}, {}, Counter()
    def team(src):
        if src is None: return None
        if 'entry' in src: return src['entry']
        return (win if 'winner' in src else lose).get(src.get('winner') or src.get('loser'), '?')
    pending = list(specs)
    while pending:
        progressed = False
        for s in list(pending):
            h, a = team(s.home), team(s.away)
            if '?' in (h, a): continue
            pending.remove(s); progressed = True
            if s.bye: win[s.key], lose[s.key] = h, None; continue
            if s.bracket == 'final_reset' and win.get('F') == a: continue
            w, l = (h, a) if rng.random() < .5 else (a, h)
            win[s.key], lose[s.key] = w, l; losses[l] += 1
        assert progressed
    return win, losses


@pytest.mark.parametrize('n', range(2, 33))
def test_single_elim_one_unbeaten_champion(n):
    teams = [str(i) for i in range(n)]
    specs = single_elim([entry(t) for t in teams], third_place=n >= 4)
    assert len({s.key for s in specs}) == len(specs)
    win, losses = simulate(specs, random.Random(n))
    champion = win[f'U{bracket_size(n).bit_length() - 1}-1']
    assert champion in teams and losses[champion] == 0


def test_byes_go_to_top_seeds():
    first = [s for s in single_elim([entry(t) for t in 'ABCDE']) if s.round_no == 1]
    assert [(s.home, s.bye) for s in first if s.bye] == [({'entry': 'A'}, True), ({'entry': 'B'}, True), ({'entry': 'C'}, True)]


def test_two_leg_round_swaps_home_in_first_leg():
    legs = [s for s in single_elim([entry(t) for t in 'ABCD'], two_leg_rounds=(1,)) if s.key == 'U1-1']
    assert [(s.leg, s.home, s.away) for s in legs] == [(1, {'entry': 'D'}, {'entry': 'A'}), (2, {'entry': 'A'}, {'entry': 'D'})]


@pytest.mark.parametrize('n', range(3, 33))
@pytest.mark.parametrize('reset', [False, True])
def test_double_elim_two_losses_out(n, reset):
    teams = [str(i) for i in range(n)]
    specs = double_elim([entry(t) for t in teams], reset)
    assert len({s.key for s in specs}) == len(specs)
    win, losses = simulate(specs, random.Random(n * 2 + reset))
    champion = win.get('F2') or win['F']
    assert losses[champion] <= 1
    for t in teams:
        if t != champion: assert losses[t] == 2 or (losses[t] == 1 and not reset)


def test_pots_one_team_from_each_pot_and_reproducible():
    groups = pots_draw(list(range(12)), 4, seed=7)
    assert groups == pots_draw(list(range(12)), 4, seed=7)
    for pot in range(3):
        assert sorted(g[pot] for g in groups) == list(range(pot * 4, pot * 4 + 4))


def test_snake():
    assert snake_draw(list(range(8)), 4) == [[0, 7], [1, 6], [2, 5], [3, 4]]


def test_group_sizes_differ_by_one():
    assert group_sizes(10, 3) == [4, 3, 3]


def label(s): return f"{'ABCDEFGH'[s['group'] - 1]}{s['place']}" if 'group' in s else f"3-{s['rank']}"


def test_two_groups_cross():
    first = [(label(s.home), label(s.away)) for s in single_elim(group_scheme(2, 2)) if s.round_no == 1]
    assert first == [('A1', 'B2'), ('B1', 'A2')]


@pytest.mark.parametrize('groups', [4, 8])
def test_group_mates_meet_only_in_final(groups):
    seeds = group_scheme(groups, 2)
    size = bracket_size(len(seeds)); rounds = size.bit_length() - 1
    for i, a in enumerate(seeds):
        for j, b in enumerate(seeds):
            if i < j and a['group'] == b['group']:
                assert meeting_round(size, i + 1, j + 1) == rounds


def places(rows): return [(r.team, r.place, r.tied) for r in rows]


def test_head_to_head_beats_goal_difference():
    res = [R('A', 'B', 1, 0), R('B', 'C', 9, 0), R('C', 'A', 1, 0), R('A', 'D', 1, 0), R('B', 'D', 0, 1), R('C', 'D', 1, 0)]
    # A, B, C по 6? — нет: A 6, B 3, C 6. A и C равны; C выиграл личную встречу.
    assert [r.team for r in rank('ABCD', res)][:2] == ['C', 'A']


def test_three_way_cycle_falls_to_overall_then_lot():
    cycle = [R('A', 'B', 1, 0), R('B', 'C', 1, 0), R('C', 'A', 1, 0)]
    res = cycle + [R('A', 'D', 5, 0), R('B', 'D', 1, 0), R('C', 'D', 1, 0)]
    assert places(rank('ABCD', res)) == [('A', 1, False), ('B', 2, True), ('C', 2, True), ('D', 4, False)]
    res = cycle + [R(t, 'D', 1, 0) for t in 'ABC']
    assert places(rank('ABCD', res))[:3] == [('A', 1, True), ('B', 1, True), ('C', 1, True)]
    assert places(rank('ABCD', res, lot=['C', 'A', 'B']))[:3] == [('C', 1, False), ('A', 2, False), ('B', 3, False)]


def test_subgroup_reapplies_head_to_head():
    # Все четверо по 4 очка; мини-таблица делит на {B, D} и {A, C}, внутри пар решает личная встреча.
    res = [R('A', 'B', 1, 1), R('A', 'C', 0, 1), R('A', 'D', 2, 1), R('B', 'C', 2, 1), R('B', 'D', 1, 2), R('C', 'D', 1, 1)]
    assert [r.team for r in rank('ABCD', res)] == ['D', 'B', 'C', 'A']


def test_technical_points_from_regulation_and_swiss_bye():
    rows = rank('AB', [R('A', 'B', 2, 2, points=(2, 1, 0))], SWISS_CRITERIA, byes=[('B', 2)])
    assert {r.team: r.points for r in rows} == {'A': 1, 'B': 3}


def test_best_thirds_per_match():
    rows = [Row('X', played=3, points=4), Row('Y', played=2, points=3), Row('Z', played=2, points=1)]
    ordered, cutoff_tied = rank_across(rows)
    assert [r.team for r in ordered] == ['Y', 'X', 'Z'] and not cutoff_tied(2)


@pytest.mark.parametrize('n', [7, 8, 9, 10])
def test_swiss_four_rounds_without_rematches(n):
    rng = random.Random(n); teams = [str(i) for i in range(n)]; played = set(); byes = []; homes = Counter(); results = []
    for _ in range(4):
        ranked = [r.team for r in rank(teams, results, SWISS_CRITERIA, byes=[(b, 3) for b in byes])]
        pairs, bye = swiss_pairs(ranked, played, set(byes), homes)
        if bye: assert bye not in byes; byes.append(bye)
        for h, a in pairs:
            assert frozenset((h, a)) not in played; played.add(frozenset((h, a))); homes[h] += 1
            results.append(R(h, a, rng.randint(0, 4), rng.randint(0, 4)))


def test_pair_winner_aggregate_and_penalties():
    assert pair_winner(('A', 'B'), [Leg('B', 'A', 1, 0), Leg('A', 'B', 2, 0)], 2) == 'A'
    assert pair_winner(('A', 'B'), [Leg('B', 'A', 1, 0), Leg('A', 'B', 1, 0, 3, 4)], 2) == 'B'
    assert pair_winner(('A', 'B'), [Leg('B', 'A', 1, 0), Leg('A', 'B', 1, 0)], 2) is None
    assert pair_winner(('A', 'B'), [Leg('A', 'B', 1, 0)], 2) is None


def test_bracket_resolves_from_groups_and_separates_thirds():
    groups = [['a1', 'a2', 'a3'], ['b1', 'b2', 'b3'], ['c1', 'c2', 'c3']]
    results = {g: [R(t[0], t[1], 1, 0), R(t[0], t[2], 1, 0), R(t[1], t[2], g, 0)] for g, t in enumerate(groups, 1)}
    tables, outcome = group_outcome(groups, results, per_group=2, best=[{'place': 3, 'count': 2}], expected=[3, 3, 3])
    assert outcome.places[(1, 1)] == 'a1' and len(outcome.best) == 2
    specs = single_elim(group_scheme(3, 2, [{'place': 3, 'count': 2}]))
    pairs = resolve_bracket(specs, {}, outcome)
    for p in pairs.values():
        if p.home and p.away: assert p.home[0] != p.away[0]   # никто не играет с одногруппником в первом раунде


def test_group_places_wait_for_all_results_and_lot():
    groups = [['A', 'B', 'C']]
    _, outcome = group_outcome(groups, {1: [R('A', 'B', 1, 0)]}, expected=[3])
    assert outcome.places == {} and not outcome.complete


def test_grand_final_reset_only_after_lower_win():
    specs = double_elim([entry(t) for t in 'ABCD'], grand_final_reset=True)
    legs = {}
    def play(key, home, away, hg, ag): legs[key] = [Leg(home, away, hg, ag)]
    play('U1-1', 'A', 'D', 1, 0); play('U1-2', 'B', 'C', 1, 0); play('U2-1', 'A', 'B', 1, 0)
    play('L1-1', 'D', 'C', 1, 0); play('L2-1', 'D', 'B', 1, 0)
    play('F', 'A', 'D', 1, 0)
    assert resolve_bracket(specs, legs)['F2'].home is None
    play('F', 'A', 'D', 0, 1)
    assert resolve_bracket(specs, legs)['F2'].home == 'D'


@pytest.mark.parametrize('n', range(3, 17))
@pytest.mark.parametrize('kind', ['single', 'double'])
def test_resolver_plays_whole_bracket(n, kind):
    rng = random.Random(n); teams = [str(i) for i in range(n)]
    specs = (single_elim([entry(t) for t in teams], third_place=True) if kind == 'single'
             else double_elim([entry(t) for t in teams], grand_final_reset=True))
    legs = {}
    for _ in range(200):
        pairs = resolve_bracket(specs, legs)
        todo = [p for p in pairs.values() if p.home and p.away and p.winner is None and p.key not in legs]
        if not todo: break
        for p in todo: legs[p.key] = [Leg(p.home, p.away, *rng.choice([(1, 0), (0, 1)]))]
    pairs = resolve_bracket(specs, legs)
    final = 'F2' if pairs.get('F2') and pairs['F2'].home else ('F' if kind == 'double' else f'U{bracket_size(n).bit_length() - 1}-1')
    assert pairs[final].winner in teams
    assert all(p.winner or not (p.home and p.away) for p in pairs.values())


def test_group_outcome_removes_annulled_and_sinks_withdrawn():
    groups = [['A', 'B', 'C', 'D']]
    tables, _ = group_outcome(groups, {1: [R('A', 'B', 0, 3), R('C', 'D', 1, 0)]}, removed={'D'}, expected=[3])
    assert tables[0][0].team == 'B'
    assert 'D' not in [r.team for r in tables[0]]
    full = [R('A', 'B', 3, 0), R('A', 'C', 3, 0), R('A', 'D', 3, 0), R('B', 'C', 1, 0), R('B', 'D', 1, 0), R('C', 'D', 1, 0)]
    tables, outcome = group_outcome(groups, {1: full}, per_group=2, withdrawn={'A'}, expected=[6])
    assert [(r.team, r.place) for r in tables[0]] == [('B', 1), ('C', 2), ('D', 3), ('A', 4)]
    assert outcome.places[(1, 1)] == 'B' and outcome.places[(1, 2)] == 'C' and (1, 4) not in outcome.places


def test_bracket_walkover_for_withdrawn():
    specs = single_elim([entry(t) for t in 'ABCD'])
    pairs = resolve_bracket(specs, {'U1-1': [Leg('A', 'D', 1, 0)]}, withdrawn={'C'})
    assert pairs['U1-2'].winner == 'B' and pairs['U1-2'].walkover == 'home'
    assert (pairs['U2-1'].home, pairs['U2-1'].away) == ('A', 'B')
