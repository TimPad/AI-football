"""Рейтинг матча по очкам за действия, как у FotMob: 6,0 + очки за действия игрока, итог от 3 до 10.

Считается по одному матчу из того, что известно о действиях игрока, и не сравнивает его с другими —
в отличие от пилотного рейтинга по ролям (role-profile-v1), которому нужна база выступлений.
Веса — в configs/ratings/match-points-v1.json; это прикидка, а не выверенная модель.

Время событий (t, мс) — на часах участия: по ним вратарь на воротах и игроки на площадке. None — время
неизвестно: тогда вратарь определяется, только если он у команды один, а плюс-минус по голу не считается.
"""

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parents[3] / 'configs/ratings/match-points-v1.json'
SIDES = ('home', 'away')
# Порядок строк расшифровки.
PART_ORDER = (
    'goal',
    'assist',
    'shot_on_target',
    'tackle',
    'interception',
    'shot_block',
    'pass',
    'save',
    'goal_conceded',
    'team_goal',
    'team_conceded',
    'yellow',
    'red',
    'own_goal',
)
CARD_PART = {'yellow': 'yellow', 'second_yellow': 'red', 'red': 'red'}


def load_policy():
    return json.loads(POLICY_PATH.read_text())


def _other(side):
    return 'away' if side == 'home' else 'home'


def _inside(t, intervals):
    return any(a <= t < b for a, b in intervals)


def _round(value, places):
    return float(Decimal(str(round(value, 6))).quantize(Decimal(places), rounding=ROUND_HALF_UP))


def _keeper(goalkeepers, side, t):
    """Вратарь стороны в момент t: по интервалам ролей; без времени — только если вратарь один."""
    keepers = goalkeepers.get(side) or []
    if len(keepers) == 1 and (keepers[0]['intervals'] is None or t is None):
        return keepers[0]['player_id']
    if t is None:
        return None
    on = [k['player_id'] for k in keepers if k['intervals'] is None or _inside(t, k['intervals'])]
    return on[0] if len(on) == 1 else None


def _at(action):
    """Момент действия для сверки действий между собой: время записи (at), иначе t."""
    return action.get('at', action['t'])


def _tackle_moments(actions):
    return {(a['side'], _at(a)) for a in actions if a['kind'] == 'duel' and a.get('success') and _at(a) is not None}


def match_points(*, lineup, goals, cards, actions, passes, goalkeepers, presence, partial, policy):
    """lineup: [{player_id, side, display_name}]; goals: [{id, side (команда автора), player_id, assist_id,
    own_goal, t}]; cards: [{player_id, card}]; actions: размеченные действия [{kind, side, player_id, t,
    on_target, outcome, success, at — время записи для сверки отбора и возврата}] без голов (голы — из протокола); passes: {player_id: число передач};
    goalkeepers: {side: [{player_id, intervals | None}]}; presence: {player_id: интервалы на площадке};
    partial: категории с неполной разметкой."""
    points = policy['points']
    side_of = {p['player_id']: p['side'] for p in lineup}
    counts = {}
    missing = {
        'goals_total': len(goals),
        'goals_without_author': 0,
        'actions_without_player': 0,
        'goalkeeper_unknown': [s for s in SIDES if not goalkeepers.get(s)],
        'without_on_court': 0,
        'partial_categories': sorted(partial),
    }

    def add(pid, key, n=1):
        if pid is None or pid not in side_of:
            return False
        counts.setdefault(pid, {}).setdefault(key, 0)
        counts[pid][key] += n
        return True

    for g in goals:
        scored = _other(g['side']) if g.get('own_goal') else g['side']
        if g.get('own_goal'):
            add(g.get('player_id'), 'own_goal')
        elif not add(g.get('player_id'), 'goal'):
            missing['goals_without_author'] += 1
        if not g.get('own_goal'):
            add(g.get('assist_id'), 'assist')
        add(_keeper(goalkeepers, _other(scored), g['t']), 'goal_conceded')
        if g['t'] is None:
            continue
        for pid, spans in presence.items():
            side = side_of.get(pid)
            if side is None or not _inside(g['t'], spans) or _keeper(goalkeepers, side, g['t']) == pid:
                continue
            add(pid, 'team_goal' if side == scored else 'team_conceded')

    for c in cards:
        add(c.get('player_id'), CARD_PART.get(c.get('card'), 'yellow'))

    tackles = _tackle_moments(actions)
    for a in actions:
        key = None
        kind = a['kind']
        if kind == 'shot' and (a.get('on_target') or a.get('outcome') == 'saved'):
            key = 'shot_on_target'
        elif kind == 'duel' and a.get('success'):
            key = 'tackle'
        elif kind == 'recovery':
            # Возврат мяча в момент отбора своей команды — часть того же отбора, а не перехват.
            if a.get('player_id') is None and (a['side'], _at(a)) in tackles:
                continue
            key = 'interception'
        elif kind == 'shot_block':
            key = 'shot_block'
        elif kind == 'save':
            key = 'save'
        if key is None:
            continue
        pid = a.get('player_id')
        if pid is None and key == 'save':
            pid = _keeper(goalkeepers, a['side'], a['t'])
        if not add(pid, key):
            missing['actions_without_player'] += 1

    for pid, n in passes.items():
        if n:
            add(pid, 'pass', n)

    keepers = {k['player_id'] for side in SIDES for k in goalkeepers.get(side) or []}
    items = []
    for person in lineup:
        pid = person['player_id']
        mine = counts.get(pid, {})
        if not mine and pid not in keepers and pid not in presence:
            continue
        parts = []
        for key in PART_ORDER:
            if key not in mine:
                continue
            value = mine[key] * points[key]
            if key == 'pass':
                value = min(value, policy['pass_cap'])
            parts.append({'key': key, 'count': mine[key], 'points': _round(value, '0.01')})
        score = policy['base'] + sum(p['points'] for p in parts)
        if pid not in keepers and pid not in presence:
            missing['without_on_court'] += 1
        items.append(
            {
                'player_id': pid,
                'side': person['side'],
                'display_name': person.get('display_name'),
                'goalkeeper': pid in keepers,
                'score': round(score, 6),
                'rating': _round(min(policy['max'], max(policy['min'], score)), '0.1'),
                'parts': parts,
            }
        )
    authored = missing['goals_total'] - missing['goals_without_author']
    ready = not goals or authored / len(goals) >= policy['goal_authors_min']
    complete = ready and not any(
        missing[k] for k in ('goals_without_author', 'actions_without_player', 'goalkeeper_unknown', 'without_on_court')
    )
    complete = complete and not missing['partial_categories']
    best = max(items, key=lambda i: i['score'], default=None)
    for item in items:
        item.pop('score')
    return {
        'model_version': policy['model_version'],
        'ready': ready,
        'complete': complete,
        'best_player_id': best['player_id'] if best else None,
        'items': items,
        'missing': missing,
    }
