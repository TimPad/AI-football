"""Таблица и порядок мест: личные встречи по правилу УЕФА, затем общие показатели, затем жребий."""
from dataclasses import dataclass, field
from fractions import Fraction

H2H = ('h2h_points', 'h2h_goal_diff', 'h2h_goals')
DEFAULT_CRITERIA = ('points', *H2H, 'goal_diff', 'goals_for', 'wins', 'lot')
SWISS_CRITERIA = ('points', 'buchholz', 'goal_diff', 'goals_for', 'wins', 'lot')


@dataclass(frozen=True)
class Result:
    home: str
    away: str
    home_goals: int
    away_goals: int
    points: tuple[int, int, int] = (3, 1, 0)  # победа, ничья, поражение — из регламента матча


@dataclass
class Row:
    team: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0
    buchholz: int = 0
    place: int = 0
    tied: bool = False

    @property
    def goal_diff(self): return self.goals_for - self.goals_against


def _table(teams, results, byes=()):
    rows = {t: Row(t) for t in teams}
    for r in results:
        if r.home not in rows or r.away not in rows: continue
        win, draw, loss = r.points
        for side, gf, ga in ((r.home, r.home_goals, r.away_goals), (r.away, r.away_goals, r.home_goals)):
            row = rows[side]; row.played += 1; row.goals_for += gf; row.goals_against += ga
            if gf > ga: row.won += 1; row.points += win
            elif gf == ga: row.drawn += 1; row.points += draw
            else: row.lost += 1; row.points += loss
    for team, win_points in byes:
        # Отдых в швейцарке — победа без мячей.
        if team in rows: rows[team].played += 1; rows[team].won += 1; rows[team].points += win_points
    return rows


def _value(row, criterion):
    return {'points': row.points, 'goal_diff': row.goal_diff, 'goals_for': row.goals_for,
            'wins': row.won, 'buchholz': row.buchholz}[criterion]


def _split(group, key):
    parts = {}
    for team in group: parts.setdefault(key(team), []).append(team)
    return [parts[k] for k in sorted(parts, reverse=True)]


def rank(teams, results, criteria=DEFAULT_CRITERIA, lot=(), byes=()):
    """Строки таблицы по местам. lot — порядок по жребию; равные без жребия получают общее место и tied."""
    rows = _table(teams, results, byes)
    if 'buchholz' in criteria:
        for r in results:
            if r.home in rows and r.away in rows:
                rows[r.home].buchholz += rows[r.away].points; rows[r.away].buchholz += rows[r.home].points
    lot_index = {team: i for i, team in enumerate(lot)}

    def order(group, start):
        if len(group) <= 1: return [group]
        i = start
        while i < len(criteria):
            criterion = criteria[i]
            if criterion == 'lot':
                if all(t in lot_index for t in group):
                    return [[t] for t in sorted(group, key=lot_index.__getitem__)]
                return [group]
            if criterion in H2H:
                end = i
                while end < len(criteria) and criteria[end] in H2H: end += 1
                block = criteria[i:end]
                mini = _table(group, [r for r in results if r.home in group and r.away in group])
                names = {'h2h_points': 'points', 'h2h_goal_diff': 'goal_diff', 'h2h_goals': 'goals_for'}
                parts = _split(group, lambda t: tuple(_value(mini[t], names[c]) for c in block))
                if len(parts) > 1:
                    # Разделившиеся подгруппы заново проходят личные встречи только между собой.
                    return [sub for part in parts for sub in order(part, i)]
                i = end; continue
            parts = _split(group, lambda t: _value(rows[t], criterion))
            if len(parts) > 1:
                return [sub for part in parts for sub in order(part, i + 1)]
            i += 1
        return [group]

    blocks = order(sorted(teams), 0)
    ranked = []; place = 1
    for block in blocks:
        for team in block:
            row = rows[team]; row.place = place; row.tied = len(block) > 1; ranked.append(row)
        place += len(block)
    return ranked


def rank_across(rows, lot=()):
    """Команды одного места из разных групп: очки, разница и забитые за матч, затем жребий.
    Возвращает порядок и функцию «граница после count мест зависит от жребия»."""
    lot_index = {team: i for i, team in enumerate(lot)}
    def key(row):
        games = max(row.played, 1)
        return (Fraction(row.points, games), Fraction(row.goal_diff, games), Fraction(row.goals_for, games))
    ordered = sorted(rows, key=lambda r: (tuple(-v for v in key(r)), lot_index.get(r.team, len(lot_index)), r.team))
    def cutoff_tied(count):
        if count >= len(ordered): return False
        a, b = ordered[count - 1], ordered[count]
        return key(a) == key(b) and not (a.team in lot_index and b.team in lot_index)
    return ordered, cutoff_tied
