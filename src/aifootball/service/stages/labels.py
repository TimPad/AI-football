"""Подписи этапов, раундов и источников простыми словами."""
LETTERS = 'ABCDEFGHIJKLMNOP'


def group_name(group_no): return f'Группа {LETTERS[group_no - 1]}'


def upper_round_name(round_no, total, double=False):
    left = total - round_no
    if left == 0: return 'Финал верхней сетки' if double else 'Финал'
    if left == 1: return 'Полуфинал'
    return f'1/{2 ** left} финала'


def round_name(kind, bracket, round_no, total_upper):
    if bracket in ('upper', None) and kind in ('single_elim', 'double_elim'):
        return upper_round_name(round_no, total_upper, kind == 'double_elim')
    return {'lower': f'Нижняя сетка · Раунд {round_no}', 'third': 'Матч за 3-е место',
            'final': 'Гранд-финал', 'final_reset': 'Переигровка финала'}.get(bracket, f'Тур {round_no}')


def pair_label(kind, fixture, total_upper, legs=1):
    if kind == 'groups': base = f'{group_name(fixture.group_no)} · Тур {fixture.round_no}'
    elif kind in ('round_robin', 'swiss'): base = f'Тур {fixture.round_no}'
    else: base = round_name(kind, fixture.bracket, fixture.round_no, total_upper)
    return f'{base} · Матч {fixture.leg}' if legs > 1 else base


def source_label(source, numbers):
    """numbers — номера пар этапа по ключу, чтобы писать «Победитель пары 3»."""
    if source is None: return 'Пропуск хода'
    if 'winner' in source: return f"Победитель пары {numbers.get(source['winner'], '?')}"
    if 'loser' in source: return f"Проигравший пары {numbers.get(source['loser'], '?')}"
    if 'group' in source: return f"{LETTERS[source['group'] - 1]}{source['place']}"
    if 'best' in source: return f"Лучшая {source['best']}-я №{source['rank']}"
    if 'stage_place' in source: return f"{source['stage_place']}-е место"
    return 'Соперник определится'
