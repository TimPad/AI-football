"""Командная сводка действий матча: ручная версия действий и события по мячу из видеоанализа.

Полнота категории берётся из объявления версии и не выводится из числа записей.
Неизвестный исход остаётся отдельным числом и не входит в знаменатель процента.
Ручная версия главнее: автоматические строки добавляются только в категории, которых в ней нет.
Автоматическая категория всегда неполная — распознаётся не каждая передача.

Передачи для карты (passes) — только с точками начала и конца, в координатах площадки (метры, как на видео);
сводка по исполнителям (pass_players) — по всем передачам периода, в том числе без координат.
Средние позиции игроков (positions) — по видео: тепловые карты треков в таймах отчёта, развёрнутые к одному
направлению атаки (positions_orientation); у матча без видеоанализа их нет.
"""

import math
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from aifootball.service.analysis.aggregation import period_fragments
from aifootball.service.errors import DomainError
from aifootball.service.ratings.models import ActionVersion, RatingMatchPublication, is_auto

SIDES = ('home', 'away')
# (ключ, подпись, группа, категория полноты, вид значения)
ROWS = [
    ('shots_total', 'Всего ударов', 'shots', 'shots', 'count'),
    ('shots_on_target', 'Удары в створ', 'shots', 'shots', 'count'),
    ('shots_off_target', 'Удары мимо ворот', 'shots', 'shots', 'count'),
    ('shots_blocked', 'Заблокированные удары', 'shots', 'shots', 'count'),
    ('passes_total', 'Передачи', 'passes', 'passes', 'count'),
    ('passes_accurate', 'Точные передачи', 'passes', 'passes', 'percent'),
    ('carries_successful', 'Удачные ведения', 'passes', 'carries', 'percent'),
    ('duels_won', 'Выигранные единоборства', 'defense', 'duels', 'percent'),
    ('recoveries', 'Возвраты мяча', 'defense', 'recoveries', 'count'),
    ('shot_blocks', 'Блокировки ударов', 'defense', 'shot_blocks', 'count'),
    ('turnovers', 'Потери', 'defense', 'turnovers', 'count'),
    ('saves', 'Сейвы', 'goalkeeping', 'saves', 'count'),
    ('distribution_accurate', 'Точные вводы вратаря', 'goalkeeping', 'distribution', 'percent'),
    ('errors', 'Ошибки', 'defense', 'errors', 'count'),
]


def _coverage(doc, category):
    items = (doc.get('completeness') or {}).get(category) or []
    full = [[0, doc['duration_ms']]]
    if any(
        i['status'] == 'complete'
        and i.get('player_ids') is None
        and (i.get('intervals') is None or i['intervals'] == full)
        for i in items
    ):
        return 'complete'
    return 'partial' if any(i['status'] in ('complete', 'partial') for i in items) else 'unknown'


def _periods(version):
    if version.document.get('clock_basis') != 'game':
        return []
    rules = (version.provenance or {}).get('regulation') or {}
    regular = list(rules.get('periods_s') or [])
    extra = rules.get('extra') or {}
    extra_periods = list(extra.get('periods_s') or []) if extra.get('enabled') else []
    bounds = []
    cursor = 0
    for index, seconds in enumerate(regular + extra_periods, 1):
        label = f'{index}-й тайм' if index <= len(regular) else f'Доп. время {index - len(regular)}'
        bounds.append({'key': str(index), 'label': label, 'start_ms': cursor, 'end_ms': cursor + seconds * 1000})
        cursor += seconds * 1000
    return bounds


def _period_of(record, bounds):
    if record.get('period') is not None:
        return str(record['period'])
    start = record.get('start_ms')
    if start is None or record.get('clock_basis', 'game') != 'game':
        return None
    return next((b['key'] for b in bounds if b['start_ms'] <= start < b['end_ms']), None)


def _count(items):
    return {'value': len(items), 'numerator': None, 'denominator': None, 'unknown': 0}


def _ratio(items, key='success'):
    known = [i for i in items if i.get(key) is not None]
    good = sum(1 for i in known if i[key])
    return {
        'value': round(100 * good / len(known), 1) if known else None,
        'numerator': good,
        'denominator': len(known),
        'unknown': len(items) - len(known),
    }


def _on_target(shot):
    return shot.get('on_target') is True or shot.get('outcome') in ('goal', 'saved')


def _values(records, blocked_ids):
    by_kind = lambda kind: [r for r in records if r['kind'] == kind]
    shots = [r for r in records if r.get('counts_as_shot')]
    return {
        'shots_total': _count(shots),
        'shots_on_target': _count([s for s in shots if _on_target(s)]),
        'shots_off_target': _count(
            [
                s
                for s in shots
                if s.get('outcome') == 'off_target' or (s.get('on_target') is False and s['id'] not in blocked_ids)
            ]
        ),
        'shots_blocked': _count([s for s in shots if s['id'] in blocked_ids]),
        'passes_total': _count(by_kind('pass')),
        'passes_accurate': _ratio(by_kind('pass')),
        'carries_successful': _ratio(by_kind('carry')),
        'duels_won': _ratio(by_kind('duel')),
        'recoveries': _count(by_kind('recovery')),
        'shot_blocks': _count(by_kind('shot_block')),
        'turnovers': _count(by_kind('turnover')),
        'saves': _count(by_kind('save')),
        'distribution_accurate': _ratio(by_kind('distribution')),
        'errors': _count(by_kind('error')),
    }


def _length(a, b):
    return round(math.hypot(b[0] - a[0], b[1] - a[1]), 1)


def _pass_points(records, period_of, source):
    """Передачи с обеими точками — стрелки карты; исход неизвестен — success None."""
    return [
        {
            'id': str(r['id']),
            'side': r['side'],
            'player_id': r.get('player_id'),
            'recipient_id': r.get('recipient_id'),
            'start_xy': [float(v) for v in r['start_xy']],
            'end_xy': [float(v) for v in r['end_xy']],
            'length_m': _length(r['start_xy'], r['end_xy']),
            'success': r.get('success'),
            'period': period_of(r),
            'start_ms': r.get('start_ms'),
            'attacking_direction': r.get('attacking_direction') or 'unknown',
            'source': source,
            'verified': r.get('review') != 'auto',
        }
        for r in records
        if r.get('start_xy') and r.get('end_xy')
    ]


def _pass_players(records):
    """Передачи по исполнителю (player_id None — автор не определён); точность — по известному исходу."""
    groups = {}
    for r in records:
        groups.setdefault((r['side'], r.get('player_id')), []).append(r)
    rows = []
    for (side, player_id), items in groups.items():
        known = [i for i in items if i.get('success') is not None]
        lengths = [_length(i['start_xy'], i['end_xy']) for i in items if i.get('start_xy') and i.get('end_xy')]
        rows.append(
            {
                'side': side,
                'player_id': player_id,
                'total': len(items),
                'accurate': sum(1 for i in known if i['success']),
                'known': len(known),
                'length_m': round(sum(lengths) / len(lengths), 1) if lengths else None,
                'verified': sum(1 for i in items if i.get('review') != 'auto'),
            }
        )
    return sorted(
        rows, key=lambda r: (SIDES.index(r['side']), r['player_id'] is None, -r['total'], str(r['player_id']))
    )


# Вид события по мячу -> категория полноты строк сводки.
AUTO_CATEGORY = {'pass': 'passes'}


def _cv_periods(run):
    """'all' — основной период прогона, 'N' — тайм hN отчёта."""
    periods = {p['key']: p for p in run.report['periods']}
    out = [{'key': 'all', 'label': 'Весь матч', 'spans': periods[run.manifest['primary_period_key']]['spans']}]
    for key in sorted(k for k in periods if k[:1] == 'h' and k[1:].isdigit()):
        out.append({'key': key[1:], 'label': f'{key[1:]}-й тайм', 'spans': periods[key]['spans']})
    return out


def _auto_rows(run, period):
    """Строки из событий прогона CV: стороны по side_map. None — для периода нет данных видеоанализа."""
    bounds = next((p for p in _cv_periods(run) if p['key'] == period), None)
    if bounds is None:
        return None
    doc = run.events or {}
    categories = {AUTO_CATEGORY[k] for k in doc.get('kinds', []) if k in AUTO_CATEGORY}
    inside = lambda e: any(a <= e['start_s'] <= b for a, b in bounds['spans'])
    records = [
        {'kind': e['kind'], 'success': e['success'], 'side': run.side_map.get(e['team'])}
        for e in doc.get('events', [])
        if inside(e)
    ]
    values = {side: _values([r for r in records if r['side'] == side], set()) for side in SIDES}
    return [
        {
            'key': key,
            'label': label,
            'group': group,
            'category': category,
            'unit': unit,
            'coverage': 'partial',
            'source': 'cv_auto',
            'home': values['home'][key],
            'away': values['away'][key],
        }
        for key, label, group, category, unit in ROWS
        if category in categories
    ]


# Центры команд ближе этого — направление атаки по ним не определяем.
ATTACK_MIN_GAP_M = 0.5


def _centroid(heatmap, cell, length, width):
    """(x, y, секунды) — средняя точка тепловой карты (клетки cell м, первый индекс — x) или None без наблюдений."""
    total = sx = sy = 0.0
    for i, column in enumerate(heatmap or []):
        for j, seconds in enumerate(column):
            if seconds > 0:
                total += seconds
                sx += seconds * min((i + 0.5) * cell, length)
                sy += seconds * min((j + 0.5) * cell, width)
    return (sx / total, sy / total, total) if total > 0 else None


def _cv_attack(run):
    """{ключ периода отчёта: {команда: 'right' | 'left'}} — куда атакует команда A/B в координатах площадки.

    Правило то же, что у обработчика (perception.teams.defending_sides): свои ворота у той команды, чей центр
    полевых ближе к ним. Центр — по тепловой карте команды за период; близкие центры — направление неизвестно.
    """
    pitch = run.report['pitch']
    size = (pitch.get('cell_m', 1), pitch['length_m'], pitch['width_m'])
    out = {}
    for period in run.report['periods']:
        teams = period.get('teams') or {}
        centers = {t: _centroid((teams.get(t) or {}).get('heatmap_s'), *size) for t in ('A', 'B')}
        if None in centers.values() or abs(centers['A'][0] - centers['B'][0]) < ATTACK_MIN_GAP_M:
            continue
        left = 'A' if centers['A'][0] < centers['B'][0] else 'B'
        out[period['key']] = {left: 'right', 'B' if left == 'A' else 'A': 'left'}
    return out


def _report_key(run, period):
    """Ключ периода отчёта для тайма передачи ('1' -> 'h1'); без тайма — основной период."""
    return f'h{period}' if period else run.manifest['primary_period_key']


def _cv_positions(run, period, people):
    """Средние позиции игроков по видео за период и как они развёрнуты.

    Позиция — средняя точка тепловых карт треков игрока в таймах отчёта (взвешена секундами). Если направление
    атаки известно во всех таймах, поле развёрнуто так, что хозяева атакуют вправо, гости — влево ('attack');
    иначе в чётных таймах поле повёрнуто на 180°: в перерыве команды меняются воротами ('halves').
    Без деления на таймы и без направления — координаты как на видео ('camera').
    """
    assigned, sides = people
    periods = {p['key']: p for p in run.report['periods']}
    halves = sorted((k for k in periods if k[:1] == 'h' and k[1:].isdigit()), key=lambda k: int(k[1:]))
    if period == 'all':
        keys = halves or [run.manifest['primary_period_key']]
    else:
        keys = [f'h{period}'] if f'h{period}' in periods else []
    if not keys:
        return [], None
    attack = _cv_attack(run)
    known = all(k in attack for k in keys)
    orientation = 'attack' if known else 'halves' if halves else 'camera'
    pitch = run.report['pitch']
    length, width = float(pitch['length_m']), float(pitch['width_m'])
    sums = {}
    for key in keys:
        number = int(key[1:]) if key in halves else 1
        for row in period_fragments(periods[key], pitch).values():
            team = row.get('team')
            side = run.side_map.get(team)
            player = assigned.get(row['track_id'])
            if player is None or side not in SIDES or sides.get(player) != side:
                continue
            center = _centroid(row.get('heatmap_s'), pitch.get('cell_m', 1), length, width)
            if center is None:
                continue
            x, y, seconds = center
            flip = (side == 'home') == (attack[key][team] == 'left') if known else number % 2 == 0
            if flip:
                x, y = length - x, width - y
            acc = sums.setdefault((side, player), [0.0, 0.0, 0.0])
            acc[0] += x * seconds
            acc[1] += y * seconds
            acc[2] += seconds
    positions = [
        {'side': side, 'player_id': player, 'x': round(sx / s, 2), 'y': round(sy / s, 2), 'observed_s': round(s, 1)}
        for (side, player), (sx, sy, s) in sums.items()
    ]
    return sorted(positions, key=lambda p: (SIDES.index(p['side']), str(p['player_id']))), orientation


def _video_ball(run):
    """Чем найден мяч передач прогона: общим детектором игроков (его модель в манифесте), своей моделью мяча на
    записи трансляции (поворотная камера — в проверках есть привязка кадров) или своей моделью мяча зала.
    Замер по ручным журналам делался только на своей модели и неподвижных камерах залов."""
    ball = ((run.events or {}).get('ball') or {}).get('model')
    detector = ((run.manifest or {}).get('processor') or {}).get('model')
    if ball and ball == detector:
        return 'general'
    return 'broadcast_model' if 'camera_registration' in (run.checks or {}) else 'ball_model'


def _auto_passes(run, period, people):
    """Передачи прогона CV как записи сводки. Исполнитель и адресат — игроки назначенных фрагментов той же
    стороны (как в автоматической версии действий); адресат — только у точной передачи."""
    assigned, sides = people
    periods = _cv_periods(run)
    bounds = next((p for p in periods if p['key'] == period), None)
    if bounds is None:
        return []
    halves = [p for p in periods if p['key'] != 'all']
    pitch = run.report['pitch']
    attack = _cv_attack(run)
    inside = lambda t, spans: any(a <= t <= b for a, b in spans)
    clip = lambda xy: [
        min(max(float(xy[0]), 0.0), float(pitch['length_m'])),
        min(max(float(xy[1]), 0.0), float(pitch['width_m'])),
    ]
    records = []
    for index, e in enumerate((run.events or {}).get('events', [])):
        side = run.side_map.get(e.get('team'))
        if e['kind'] != 'pass' or side not in SIDES or not inside(e['start_s'], bounds['spans']):
            continue
        author = assigned.get(e['track_id'])
        author = author if author is not None and sides.get(author) == side else None
        recipient = assigned.get(e.get('recipient_track_id')) if e['success'] else None
        if recipient is not None and (recipient == author or sides.get(recipient) != side):
            recipient = None
        half = next((h['key'] for h in halves if inside(e['start_s'], h['spans'])), None)
        records.append(
            {
                # Тот же UUID, что у передачи в автоматической версии действий (ratings.auto.actions_document).
                'id': uuid5(NAMESPACE_URL, f'aifootball:cv-auto:{run.id}:{index}'),
                'kind': 'pass',
                'side': side,
                'player_id': author,
                'recipient_id': recipient,
                'start_xy': clip(e['start_xy']),
                'end_xy': clip(e['end_xy']),
                'success': bool(e['success']),
                'period': half,
                'start_ms': max(0, round(e['start_s'] * 1000)),
                # Направление атаки по видео: обработчик его не выдаёт, оно выводится из центров команд в тайме.
                'attacking_direction': attack.get(_report_key(run, half), {}).get(e['team'], 'unknown'),
                'review': 'auto',
            }
        )
    return records


def _reviewed_version(db, match_id, run):
    """Последняя подтверждённая проверка передач этого видеоанализа: ручная версия действий из него, где хотя бы
    одна передача из видео проверена человеком. Зрителю она видна без отдельной публикации действий."""
    versions = db.scalars(
        select(ActionVersion)
        .where(
            ActionVersion.match_id == match_id,
            ActionVersion.status == 'confirmed',
            ActionVersion.source_analysis_run_id == run.id,
        )
        .order_by(ActionVersion.revision.desc())
    )
    for version in versions:
        if is_auto(version):
            continue
        actions = version.document.get('actions', [])
        if any(a['kind'] == 'pass' and a.get('review') == 'checked' for a in actions):
            return version
    return None


def _reviewed_passes(version, run, period):
    """Передачи проверки (без отклонённых) за период видеоанализа: тайм и направление атаки — по видео."""
    bounds = next((p for p in _cv_periods(run) if p['key'] == period), None)
    if bounds is None:
        return []
    halves = [p for p in _cv_periods(run) if p['key'] != 'all']
    attack = _cv_attack(run)
    team_of = {side: team for team, side in run.side_map.items()}
    inside = lambda t, spans: any(a <= t <= b for a, b in spans)
    records = []
    for r in version.canonical_actions or []:
        if r['kind'] != 'pass' or r.get('side') not in SIDES or r.get('start_ms') is None:
            continue
        t = r['start_ms'] / 1000
        if not inside(t, bounds['spans']):
            continue
        half = next((h['key'] for h in halves if inside(t, h['spans'])), None)
        direction = r.get('attacking_direction') or 'unknown'
        if direction == 'unknown':
            direction = attack.get(_report_key(run, half), {}).get(team_of.get(r['side']), 'unknown')
        records.append({**r, 'period': half, 'attacking_direction': direction})
    return records


def _with_review(stats, version, run):
    """Передачи из проверки вместо событий видео: строки, карта и сводка по игрокам — с пометкой cv_reviewed."""
    records = _reviewed_passes(version, run, stats['period'])
    values = {side: _values([r for r in records if r['side'] == side], set()) for side in SIDES}
    rows = [r for r in stats['rows'] if r['category'] != 'passes']
    for row in (r for r in stats['rows'] if r['category'] == 'passes'):
        rows.append(
            {**row, 'source': 'cv_reviewed', 'home': values['home'][row['key']], 'away': values['away'][row['key']]}
        )
    stats['rows'] = rows
    stats['passes'] = _pass_points(records, lambda r: r['period'], 'cv_reviewed')
    stats['pass_players'] = _pass_players(records)
    return stats


# Разметка ударов и защиты по видео в кабинете: категории, которые она объявляет, и виды её действий.
TAGGED_CATEGORIES = ('shots', 'saves', 'shot_blocks', 'duels', 'recoveries')
TAGGED_KINDS = ('shot', 'goal', 'save', 'shot_block', 'duel', 'recovery')


def _tagged_version(db, match_id, run):
    """Последняя подтверждённая разметка ударов и защиты этого видеоанализа: ручная версия действий из него,
    объявившая полноту хотя бы одной категории разметки. Зрителю она видна без отдельной публикации действий."""
    versions = db.scalars(
        select(ActionVersion)
        .where(
            ActionVersion.match_id == match_id,
            ActionVersion.status == 'confirmed',
            ActionVersion.source_analysis_run_id == run.id,
        )
        .order_by(ActionVersion.revision.desc())
    )
    for version in versions:
        if not is_auto(version) and any(_coverage(version.document, c) != 'unknown' for c in TAGGED_CATEGORIES):
            return version
    return None


def _tagged_records(version, run, period):
    """Действия разметки за период видеоанализа: тайм — по интервалам видео; match_ms — время матча
    (смещение тайма по регламенту + время от его начала на записи). Гол протокола без времени записи — в свой
    тайм по протоколу и в весь матч."""
    periods = _cv_periods(run)
    bounds = next((p for p in periods if p['key'] == period), None)
    if bounds is None:
        return []
    halves = [p for p in periods if p['key'] != 'all']
    regular = (((version.provenance or {}).get('regulation') or {}).get('periods_s')) or []
    inside = lambda t, spans: any(a <= t <= b for a, b in spans)
    records = []
    for r in version.canonical_actions or []:
        if r['kind'] not in TAGGED_KINDS or r.get('side') not in SIDES:
            continue
        if r.get('start_ms') is None or r.get('clock_basis') != 'video':
            half = str(r['period']) if r['kind'] == 'goal' and r.get('period') else None
            if half is not None and period in ('all', half):
                records.append({**r, 'period': half, 'match_ms': None})
            continue
        t = r['start_ms'] / 1000
        if not inside(t, bounds['spans']):
            continue
        index = next((i for i, h in enumerate(halves) if inside(t, h['spans'])), None)
        match_ms = None
        if index is not None:
            start = min(a for a, _ in halves[index]['spans'])
            match_ms = round(sum(regular[:index]) * 1000 + (t - start) * 1000)
        records.append({**r, 'period': halves[index]['key'] if index is not None else None, 'match_ms': match_ms})
    return records


def _with_tagging(stats, version, run):
    """Строки ударов, вратарей и защиты из разметки по видео — в категории, которых нет в ручной версии;
    удары с отмеченной точкой — на карту ударов."""
    have = {r['category'] for r in stats['rows'] if r['source'] == 'manual'}
    categories = [c for c in TAGGED_CATEGORIES if c not in have and _coverage(version.document, c) != 'unknown']
    if not categories:
        return stats
    records = _tagged_records(version, run, stats['period'])
    blocked = {r.get('shot_id') for r in records if r['kind'] == 'shot_block' and r.get('shot_id')}
    values = {side: _values([r for r in records if r['side'] == side], blocked) for side in SIDES}
    rows = [r for r in stats['rows'] if r['category'] not in categories]
    for key, label, group, category, unit in ROWS:
        if category in categories:
            rows.append(
                {
                    'key': key,
                    'label': label,
                    'group': group,
                    'category': category,
                    'unit': unit,
                    'coverage': _coverage(version.document, category),
                    'source': 'manual',
                    'home': values['home'][key],
                    'away': values['away'][key],
                }
            )
    order = {row[0]: i for i, row in enumerate(ROWS)}
    stats['rows'] = sorted(rows, key=lambda r: order.get(r['key'], len(order)))
    stats['coverage'] = {**stats['coverage'], **{c: _coverage(version.document, c) for c in categories}}
    if 'shots' in categories:
        stats['shots'] = [
            {
                'id': r['id'],
                'side': r['side'],
                'player_id': r.get('player_id'),
                'x': r['start_xy'][0],
                'y': r['start_xy'][1],
                'goal': bool(r.get('counts_as_player_goal')),
                'on_target': _on_target(r),
                'blocked': r['id'] in blocked,
                'outcome': r.get('outcome') or 'unknown',
                'period': r['period'],
                'start_ms': r['match_ms'],
            }
            for r in records
            if r.get('counts_as_shot') and r.get('start_xy')
        ]
    return stats


def _public_tagging(db, match_id, stats, run):
    version = _tagged_version(db, match_id, run)
    return _with_tagging(stats, version, run) if version else stats


def _with_events(stats, run, published, people):
    """Добавляет автоматические строки в категории, которых нет в ручной версии."""
    rows = _auto_rows(run, stats['period'])
    if not rows:
        return stats
    have = {r['category'] for r in stats['rows']}
    extra = [r for r in rows if r['category'] not in have]
    if not extra:
        return stats
    stats['rows'] = stats['rows'] + extra
    stats['coverage'] = {**stats['coverage'], **{r['category']: 'partial' for r in extra}}
    stats['source'] = {**stats['source'], 'kind': 'mixed', 'run_id': run.id, 'run_published': published}
    if any(r['category'] == 'passes' for r in extra):
        records = _auto_passes(run, stats['period'], people)
        stats['passes'] = _pass_points(records, lambda r: r['period'], 'cv_auto')
        stats['pass_players'] = _pass_players(records)
        stats['video_ball'] = _video_ball(run)
    return stats


def auto_action_stats(run, *, published, period='all', people=({}, {})):
    """Сводка только из событий видеоанализа: ручной версии действий нет.
    Тайм, которого нет в видеоанализе (запись не разделена на таймы), — пустая сводка, а не ошибка:
    периоды странице задаёт протокол."""
    periods = _cv_periods(run)
    rows = _auto_rows(run, period) or []
    pitch = run.report['pitch']
    records = _auto_passes(run, period, people) if any(r['category'] == 'passes' for r in rows) else []
    positions, orientation = _cv_positions(run, period, people)
    return {
        'source': {
            'kind': 'cv_auto',
            'action_version_id': None,
            'run_id': run.id,
            'revision': run.revision,
            'status': run.status,
            'published': published,
            'run_published': published,
            'clock_basis': 'video',
            'analysis_scope': 'continuous_excerpt' if run.checks.get('partial') else 'full_match',
        },
        'periods': [{'key': p['key'], 'label': p['label']} for p in periods],
        'period': period,
        'untimed': 0,
        'coverage': {r['category']: 'partial' for r in rows},
        'rows': rows,
        'shots': [],
        'passes': _pass_points(records, lambda r: r['period'], 'cv_auto'),
        'pass_players': _pass_players(records),
        'positions': positions,
        'positions_orientation': orientation,
        'pitch': {'length_m': pitch['length_m'], 'width_m': pitch['width_m']},
        'video_ball': _video_ball(run) if records else None,
    }


def team_action_stats(version, *, published, period='all'):
    doc = version.document
    records = version.canonical_actions or []
    bounds = _periods(version)
    keys = {'all', *(b['key'] for b in bounds)}
    if period not in keys:
        raise DomainError('validation', 'Такого периода нет в версии действий', status=422)
    blocked_ids = {r.get('shot_id') for r in records if r['kind'] == 'shot_block' and r.get('shot_id')}
    untimed = 0
    if period != 'all':
        selected = [r for r in records if _period_of(r, bounds) == period]
        untimed = sum(1 for r in records if _period_of(r, bounds) is None)
    else:
        selected = records
    coverage = {category: _coverage(doc, category) for category in {row[3] for row in ROWS}}
    values = {side: _values([r for r in selected if r.get('side') == side], blocked_ids) for side in SIDES}
    rows = []
    for key, label, group, category, unit in ROWS:
        present = any(values[s][key]['value'] or values[s][key]['unknown'] for s in SIDES)
        # Строка без записей и без объявленной полноты — это отсутствие источника, а не ноль.
        if not present and coverage[category] == 'unknown':
            continue
        rows.append(
            {
                'key': key,
                'label': label,
                'group': group,
                'category': category,
                'unit': unit,
                'coverage': coverage[category],
                'source': 'manual',
                'home': values['home'][key],
                'away': values['away'][key],
            }
        )
    shots = [
        {
            'id': r['id'],
            'side': r.get('side'),
            'player_id': r.get('player_id'),
            'x': r['start_xy'][0],
            'y': r['start_xy'][1],
            'goal': bool(r.get('counts_as_player_goal')),
            'on_target': _on_target(r),
            'blocked': r['id'] in blocked_ids,
            'outcome': r.get('outcome') or 'unknown',
            'period': _period_of(r, bounds),
            'start_ms': r.get('start_ms'),
        }
        for r in selected
        if r.get('counts_as_shot') and r.get('start_xy') and r.get('side') in SIDES
    ]
    passes = [r for r in selected if r['kind'] == 'pass' and r.get('side') in SIDES]
    pitch = (version.provenance or {}).get('pitch')
    return {
        'source': {
            'kind': 'manual',
            'action_version_id': version.id,
            'run_id': None,
            'revision': version.revision,
            'status': version.status,
            'published': published,
            'run_published': False,
            'clock_basis': doc.get('clock_basis'),
            'analysis_scope': doc.get('analysis_scope', 'unknown'),
        },
        'periods': [{'key': 'all', 'label': 'Весь матч'}, *({'key': b['key'], 'label': b['label']} for b in bounds)],
        'period': period,
        'untimed': untimed,
        'coverage': coverage,
        'rows': rows,
        'shots': shots,
        'passes': _pass_points(passes, lambda r: _period_of(r, bounds), 'manual'),
        'pass_players': _pass_players(passes),
        'positions': [],
        'positions_orientation': None,
        'pitch': {'length_m': pitch['length_m'], 'width_m': pitch['width_m']} if pitch else None,
    }


def _run_with_events(db, run_id):
    run = _analysis_run(db, run_id)
    return run if run is not None and run.events is not None else None


def _analysis_run(db, run_id):
    from aifootball.service.analysis.models import AnalysisRun

    return db.get(AnalysisRun, run_id) if run_id else None


def _with_positions(stats, run, db):
    """Средние позиции игроков по видеоанализу — и к ручной версии действий; без прогона их нет."""
    if run is not None:
        stats['positions'], stats['positions_orientation'] = _cv_positions(run, stats['period'], _people(db, run))
    return stats


def _people(db, run):
    """Игроки фрагментов прогона (трек -> UUID) и их стороны по составу из снимка задания."""
    from aifootball.service.analysis.models import AnalysisAssignment, AnalysisJob

    assigned = {
        a.track_id: str(a.player_id)
        for a in db.scalars(
            select(AnalysisAssignment).where(
                AnalysisAssignment.run_id == run.id, AnalysisAssignment.player_id.is_not(None)
            )
        )
    }
    job = db.get(AnalysisJob, run.job_id)
    sides = {p['player_id']: p['side'] for p in (job.context.get('rosters') or [])} if job else {}
    return assigned, sides


def public_action_stats(db, match_id, period='all'):
    from aifootball.service.matches.models import Match
    from aifootball.service.public_visibility import require_public_match

    require_public_match(db, match_id)
    pub = db.scalar(select(RatingMatchPublication).where(RatingMatchPublication.match_id == match_id))
    version = db.get(ActionVersion, pub.action_version_id) if pub and pub.action_version_id else None
    # Автоматическая версия действий — те же события прогона: сводка строится из него напрямую.
    if is_auto(version):
        version = None
    # Передачи по мячу видны гостю вместе с опубликованным видеоанализом.
    published_run = db.get(Match, match_id).published_analysis_run_id
    run = _run_with_events(db, published_run)
    if version is None and run is None:
        raise DomainError('not_found', 'Действия матча не опубликованы', status=404)
    if version is None:
        stats = auto_action_stats(run, published=True, period=period, people=_people(db, run))
        return _public_tagging(db, match_id, _public_review(db, match_id, stats, run), run)
    stats = team_action_stats(version, published=True, period=period)
    if run:
        stats = _public_review(db, match_id, _with_events(stats, run, True, _people(db, run)), run)
        stats = _public_tagging(db, match_id, stats, run)
    # Позиции — только из опубликованного видеоанализа, даже без событий по мячу.
    return _with_positions(stats, run or _analysis_run(db, published_run), db)


def _public_review(db, match_id, stats, run):
    """Передачи из видео зритель видит после подтверждённой проверки, не дожидаясь публикации действий;
    опубликованная ручная версия с передачами главнее."""
    if not any(r['category'] == 'passes' and r['source'] == 'cv_auto' for r in stats['rows']):
        return stats
    version = _reviewed_version(db, match_id, run)
    return _with_review(stats, version, run) if version else stats


def private_action_stats(db, match_id, period='all'):
    """Кабинет: последняя подтверждённая версия действий, иначе последняя на проверке;
    передачи по мячу — из активного прогона, иначе из последнего прогона с событиями."""
    from aifootball.service.analysis.models import AnalysisRun
    from aifootball.service.matches.models import Match

    match = db.get(Match, match_id)
    versions = [
        v
        for v in db.scalars(
            select(ActionVersion).where(ActionVersion.match_id == match_id).order_by(ActionVersion.revision.desc())
        )
        if not is_auto(v)
    ]
    version = next((v for v in versions if v.status == 'confirmed'), versions[0] if versions else None)
    run = _run_with_events(db, match.active_analysis_run_id) or db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.match_id == match_id, AnalysisRun.events.is_not(None))
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id)
        .limit(1)
    )
    if version is None and run is None:
        raise DomainError('not_found', 'Версий действий пока нет', status=404)
    run_published = bool(run and run.id == match.published_analysis_run_id)
    if version is None:
        return auto_action_stats(run, published=run_published, period=period, people=_people(db, run))
    pub = db.scalar(select(RatingMatchPublication).where(RatingMatchPublication.match_id == match_id))
    stats = team_action_stats(version, published=bool(pub and pub.action_version_id == version.id), period=period)
    if run:
        stats = _with_events(stats, run, run_published, _people(db, run))
    return _with_positions(stats, run or _analysis_run(db, match.active_analysis_run_id), db)
