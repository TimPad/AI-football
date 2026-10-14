from pathlib import Path
from io import BytesIO
from uuid import uuid4
from hashlib import sha256
from zipfile import ZipFile, ZipInfo
import copy
import json
import math
import pytest


def result_data(job=None):
    pitch = job['context']['pitch'] if job else {'length_m': 40, 'width_m': 20}
    manifest = {'contract_version': '1', 'run_id': str(uuid4()),
                'job_id': job['id'] if job else str(uuid4()), 'match_id': job['match_id'] if job else str(uuid4()),
                'context_hash': job['context_hash'] if job else 'a' * 64, 'primary_period_key': 'all',
                'camera_profile_id': job['context']['camera']['id'] if job else str(uuid4()),
                'source_video': {'sha256': 'b' * 64, 'duration_s': 240, 'width': 1000, 'height': 500},
                'processor': {'name': 'aifootball', 'version': '0.1.0', 'model': 'fixture'},
                'units': {'distance': 'm', 'speed': 'm/s', 'time': 's', 'heatmap': 's'}}
    heatmap = [[0.0] * math.ceil(pitch['width_m']) for _ in range(math.ceil(pitch['length_m']))]
    players = []
    for tid, obs, dist in [(1, 60, 120), (2, 120, 90), (3, 120, 100)]:
        players.append({'track_id': tid, 'label': f'Игрок {tid}', 'team': 'A' if tid != 3 else 'B',
                        'role': 'player', 'observed_s': obs, 'distance_m': dist, 'm_per_min': dist / obs * 60,
                        'hsr_m': 0, 'sprints': 0, 'vmax_ms': 2, 'heatmap_s': copy.deepcopy(heatmap)})
    report = {'schema_version': '1', 'pitch': {**pitch, 'cell_m': 1},
              'match': {'video_s': 240, 'processed_s': 240, 'teams': {'A': 'A', 'B': 'B'}},
              'periods': [{'key': 'all', 'name': 'Весь матч', 'spans': [[0, 240]], 'duration_s': 240,
                           'players': players, 'teams': {}}]}
    tracks = {'tracks': [{'track_id': p['track_id'], 'team': p['team'], 'role': p['role'],
                          'intervals': [[0, 60]] if p['track_id'] == 1 else [[120, 240]],
                          'thumb': None, 'has_metrics': True} for p in players]}
    checks = {'passed': True, 'critical_errors': [], 'partial': False, 'warnings': []}
    return manifest, report, tracks, checks


def result_zip(job=None, mutate=None, extras=None):
    manifest, report, tracks, checks = result_data(job)
    if mutate:
        mutate(manifest, report, tracks, checks)
    files = {name: json.dumps(value, allow_nan=True).encode() for name, value in
             [('report.json', report), ('track-index.json', tracks), ('checks.json', checks)]}
    files.update(extras or {})
    manifest['files'] = {name: {'size': len(raw), 'sha256': sha256(raw).hexdigest()} for name, raw in files.items()}
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        for name, raw in files.items():
            archive.writestr(name, raw)
    return buffer.getvalue()


def test_result_without_manifest_is_rejected(tmp_path):
    from aifootball.analytics.exchange import validate_result, ExchangeError
    path = tmp_path / 'result.zip'
    with ZipFile(path, 'w') as archive:
        archive.writestr('report.json', '{}')
    with pytest.raises(ExchangeError, match='manifest'):
        validate_result(path)


def test_valid_result_and_content_hash_ignore_zip_timestamps():
    from aifootball.analytics.exchange import validate_result
    raw = result_zip()
    original = validate_result(raw)
    buffer = BytesIO()
    with ZipFile(BytesIO(raw)) as source, ZipFile(buffer, 'w') as target:
        for name in source.namelist():
            target.writestr(ZipInfo(name, (2024, 1, 1, 0, 0, 0)), source.read(name))
    assert validate_result(buffer.getvalue()).content_hash == original.content_hash
    assert len(original.tracks['tracks']) == 3


@pytest.mark.parametrize('mutate', [
    lambda m, r, t, c: m.update(units={'distance': 'km'}),
    lambda m, r, t, c: r['periods'][0]['players'][0].update(distance_m=-1),
    lambda m, r, t, c: r['periods'][0]['players'][0].update(vmax_ms=float('nan')),
    lambda m, r, t, c: r['periods'][0]['players'][0].update(heatmap_s=[[1]]),
    lambda m, r, t, c: t['tracks'][0].update(intervals=[[0, 999]]),
    lambda m, r, t, c: t['tracks'].append(copy.deepcopy(t['tracks'][0])),
    lambda m, r, t, c: r['periods'][0]['players'][0].update(track_id=999),
    lambda m, r, t, c: m.update(primary_period_key='missing'),
])
def test_invalid_numbers_tracks_and_geometry(mutate):
    from aifootball.analytics.exchange import validate_result, ExchangeError
    with pytest.raises(ExchangeError):
        validate_result(result_zip(mutate=mutate))


@pytest.mark.parametrize('name', ['../outside.jpg', '/absolute.jpg', 'thumbs/../../a.jpg', 'evil.html', 'inner.zip'])
def test_archive_path_and_file_type_rejected(name):
    from aifootball.analytics.exchange import validate_result, ExchangeError
    with pytest.raises(ExchangeError):
        validate_result(result_zip(extras={name: b'x'}))


def test_unpack_limits_and_file_hash():
    from aifootball.analytics.exchange import validate_result, ExchangeError, Limits
    raw = result_zip()
    with pytest.raises(ExchangeError):
        validate_result(raw, Limits(unpacked=100))
    buffer = BytesIO()
    with ZipFile(BytesIO(raw)) as source, ZipFile(buffer, 'w') as target:
        for name in source.namelist():
            target.writestr(name, b'{}' if name == 'report.json' else source.read(name))
    with pytest.raises(ExchangeError):
        validate_result(buffer.getvalue())


@pytest.mark.parametrize('mutate', [
    lambda m,r,t,c: t['tracks'][0].update(intervals=[[0,1]]),
    lambda m,r,t,c: c.update(partial=False) or r['match'].update(processed_s=120),
    lambda m,r,t,c: r['periods'][0].update(teams={'A':{'distance_m':-1}}),
])
def test_inconsistent_coverage_and_negative_team_metrics_rejected(mutate):
    from aifootball.analytics.exchange import validate_result, ExchangeError
    with pytest.raises(ExchangeError):validate_result(result_zip(mutate=mutate))


@pytest.mark.parametrize('field',['name','label'])
def test_required_display_fields_are_validated_before_import(field):
    from aifootball.analytics.exchange import validate_result,ExchangeError
    def remove(m,r,t,c):
        target=r['periods'][0] if field=='name' else r['periods'][0]['players'][0]
        target.pop(field)
    with pytest.raises(ExchangeError):validate_result(result_zip(mutate=remove))
