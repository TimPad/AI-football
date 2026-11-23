"""Combine verified fragments; never average averages or bridge track gaps."""


def aggregate_player(fragments):
    result = {}
    for key in ['distance_m', 'observed_s', 'hsr_m', 'sprints']:
        values = [f.get(key) for f in fragments]
        result[key] = sum(values) if values and all(v is not None for v in values) else None
    # Максимум — по фрагментам, где скорость измерена: у короткого фрагмента устойчивой скорости может не быть.
    speeds = [f.get('vmax_ms') for f in fragments if f.get('vmax_ms') is not None]
    result['vmax_ms'] = max(speeds) if speeds else None
    observed, distance = result['observed_s'], result['distance_m']
    result['m_per_min'] = distance / observed * 60 if observed and distance is not None else None
    maps = [f.get('heatmap_s') for f in fragments]
    result['heatmap_s'] = (
        [[sum(row) for row in zip(*rows)] for rows in zip(*maps)] if maps and all(m is not None for m in maps) else None
    )
    result['metric_notes'] = {
        key: 'Недостаточно данных по одному или нескольким фрагментам' for key, value in result.items() if value is None
    }
    return result


def dense_heatmap(cells, length_m, width_m):
    """Разреженная тепловая карта короткого фрагмента [[x, y, секунды], …] — в сетку клеток 1 × 1 м."""
    import math

    grid = [[0.0] * math.ceil(width_m) for _ in range(math.ceil(length_m))]
    for x, y, seconds in cells:
        grid[x][y] += seconds
    return grid


def period_fragments(period, pitch):
    """Показатели фрагментов периода по номеру трека: строки таблицы игроков и короткие фрагменты (fragments)
    с тепловой картой в виде сетки — для суммы по игроку и средних позиций."""
    out = {p['track_id']: p for p in period.get('players') or []}
    for f in period.get('fragments') or []:
        out[f['track_id']] = {
            **f,
            'heatmap_s': dense_heatmap(f['heatmap_cells'], pitch['length_m'], pitch['width_m']),
        }
    return out
