"""Combine verified fragments; never average averages or bridge track gaps."""


def aggregate_player(fragments):
    result = {}
    for key in ['distance_m', 'observed_s', 'hsr_m', 'sprints']:
        values = [f.get(key) for f in fragments]
        result[key] = sum(values) if values and all(v is not None for v in values) else None
    speeds = [f.get('vmax_ms') for f in fragments]
    result['vmax_ms'] = max(speeds) if speeds and all(v is not None for v in speeds) else None
    observed, distance = result['observed_s'], result['distance_m']
    result['m_per_min'] = distance / observed * 60 if observed and distance is not None else None
    maps = [f.get('heatmap_s') for f in fragments]
    result['heatmap_s'] = [[sum(row) for row in zip(*rows)] for rows in zip(*maps)] if maps and all(m is not None for m in maps) else None
    result['metric_notes'] = {key: 'Недостаточно данных по одному или нескольким фрагментам'
                              for key, value in result.items() if value is None}
    return result
