import base64
import copy
import json
import math
from hashlib import sha256
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile, ZipInfo

import pytest


def result_data(job=None):
    pitch = job['context']['pitch'] if job else {'length_m': 40, 'width_m': 20}
    manifest = {
        'contract_version': '1',
        'run_id': str(uuid4()),
        'job_id': job['id'] if job else str(uuid4()),
        'match_id': job['match_id'] if job else str(uuid4()),
        'context_hash': job['context_hash'] if job else 'a' * 64,
        'primary_period_key': 'all',
        'camera_profile_id': job['context']['camera']['id'] if job else str(uuid4()),
        'source_video': {'sha256': 'b' * 64, 'duration_s': 240, 'width': 1000, 'height': 500},
        'processor': {'name': 'aifootball', 'version': '0.1.0', 'model': 'fixture'},
        'units': {'distance': 'm', 'speed': 'm/s', 'time': 's', 'heatmap': 's'},
    }
    heatmap = [[0.0] * math.ceil(pitch['width_m']) for _ in range(math.ceil(pitch['length_m']))]
    players = []
    for tid, obs, dist in [(1, 60, 120), (2, 120, 90), (3, 120, 100)]:
        players.append(
            {
                'track_id': tid,
                'label': f'Игрок {tid}',
                'team': 'A' if tid != 3 else 'B',
                'role': 'player',
                'observed_s': obs,
                'distance_m': dist,
                'm_per_min': dist / obs * 60,
                'hsr_m': 0,
                'sprints': 0,
                'vmax_ms': 2,
                'heatmap_s': copy.deepcopy(heatmap),
            }
        )
    report = {
        'schema_version': '1',
        'pitch': {**pitch, 'cell_m': 1},
        'match': {'video_s': 240, 'processed_s': 240, 'teams': {'A': 'A', 'B': 'B'}},
        'periods': [
            {'key': 'all', 'name': 'Весь матч', 'spans': [[0, 240]], 'duration_s': 240, 'players': players, 'teams': {}}
        ],
    }
    tracks = {
        'tracks': [
            {
                'track_id': p['track_id'],
                'team': p['team'],
                'role': p['role'],
                'intervals': [[0, 60]] if p['track_id'] == 1 else [[120, 240]],
                'thumb': None,
                'has_metrics': True,
            }
            for p in players
        ]
    }
    checks = {'passed': True, 'critical_errors': [], 'partial': False, 'warnings': []}
    return manifest, report, tracks, checks


def result_zip(job=None, mutate=None, extras=None):
    manifest, report, tracks, checks = result_data(job)
    if mutate:
        mutate(manifest, report, tracks, checks)
    files = {
        name: json.dumps(value, allow_nan=True).encode()
        for name, value in [('report.json', report), ('track-index.json', tracks), ('checks.json', checks)]
    }
    files.update(extras or {})
    manifest['files'] = {name: {'size': len(raw), 'sha256': sha256(raw).hexdigest()} for name, raw in files.items()}
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        for name, raw in files.items():
            archive.writestr(name, raw)
    return buffer.getvalue()


def test_result_without_manifest_is_rejected(tmp_path):
    from aifootball.analytics.exchange import ExchangeError, validate_result

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


@pytest.mark.parametrize(
    'mutate',
    [
        lambda m, r, t, c: m.update(units={'distance': 'km'}),
        lambda m, r, t, c: r['periods'][0]['players'][0].update(distance_m=-1),
        lambda m, r, t, c: r['periods'][0]['players'][0].update(vmax_ms=float('nan')),
        lambda m, r, t, c: r['periods'][0]['players'][0].update(heatmap_s=[[1]]),
        lambda m, r, t, c: t['tracks'][0].update(intervals=[[0, 999]]),
        lambda m, r, t, c: t['tracks'].append(copy.deepcopy(t['tracks'][0])),
        lambda m, r, t, c: r['periods'][0]['players'][0].update(track_id=999),
        lambda m, r, t, c: m.update(primary_period_key='missing'),
    ],
)
def test_invalid_numbers_tracks_and_geometry(mutate):
    from aifootball.analytics.exchange import ExchangeError, validate_result

    with pytest.raises(ExchangeError):
        validate_result(result_zip(mutate=mutate))


@pytest.mark.parametrize('name', ['../outside.jpg', '/absolute.jpg', 'thumbs/../../a.jpg', 'evil.html', 'inner.zip'])
def test_archive_path_and_file_type_rejected(name):
    from aifootball.analytics.exchange import ExchangeError, validate_result

    with pytest.raises(ExchangeError):
        validate_result(result_zip(extras={name: b'x'}))


def test_unpack_limits_and_file_hash():
    from aifootball.analytics.exchange import ExchangeError, Limits, validate_result

    raw = result_zip()
    with pytest.raises(ExchangeError):
        validate_result(raw, Limits(unpacked=100))
    buffer = BytesIO()
    with ZipFile(BytesIO(raw)) as source, ZipFile(buffer, 'w') as target:
        for name in source.namelist():
            target.writestr(name, b'{}' if name == 'report.json' else source.read(name))
    with pytest.raises(ExchangeError):
        validate_result(buffer.getvalue())


@pytest.mark.parametrize(
    'mutate',
    [
        lambda m, r, t, c: t['tracks'][0].update(intervals=[[0, 1]]),
        lambda m, r, t, c: c.update(partial=False) or r['match'].update(processed_s=120),
        lambda m, r, t, c: r['periods'][0].update(teams={'A': {'distance_m': -1}}),
    ],
)
def test_inconsistent_coverage_and_negative_team_metrics_rejected(mutate):
    from aifootball.analytics.exchange import ExchangeError, validate_result

    with pytest.raises(ExchangeError):
        validate_result(result_zip(mutate=mutate))


@pytest.mark.parametrize('field', ['name', 'label'])
def test_required_display_fields_are_validated_before_import(field):
    from aifootball.analytics.exchange import ExchangeError, validate_result

    def remove(m, r, t, c):
        target = r['periods'][0] if field == 'name' else r['periods'][0]['players'][0]
        target.pop(field)

    with pytest.raises(ExchangeError):
        validate_result(result_zip(mutate=remove))


def events_doc(**change):
    passed = {
        'kind': 'pass',
        'track_id': 1,
        'team': 'A',
        'start_s': 10.0,
        'end_s': 11.2,
        'start_xy': [10.0, 5.0],
        'end_xy': [18.0, 6.0],
        'recipient_track_id': 2,
        'success': True,
        'confidence': 0.7,
    }
    missed = {**passed, 'start_s': 30.0, 'end_s': 31.0, 'recipient_track_id': None, 'success': False}
    doc = {
        'schema_version': '1',
        'ball': {'model': 'ball/best.pt', 'sha256': 'c' * 64, 'frames_with_ball': 0.7},
        'kinds': ['pass'],
        'events': [passed, missed],
    }
    for path, value in change.items():
        *keys, last = path.split('__')
        target = doc
        for key in keys:
            target = target[int(key)] if key.isdigit() else target[key]
        target[int(last) if last.isdigit() else last] = value
    return json.dumps(doc).encode()


def result_v3(events=None, version='3'):
    return result_zip(
        mutate=lambda m, r, t, c: m.update(contract_version=version),
        extras={'events.json': events if events is not None else events_doc()},
    )


def test_contract_3_carries_validated_passes():
    from aifootball.analytics.exchange import validate_result

    result = validate_result(result_v3())
    assert result.manifest['contract_version'] == '3' and result.understanding is None
    assert [e['success'] for e in result.events['events']] == [True, False]


@pytest.mark.parametrize(
    'raw',
    [
        lambda: result_v3(version='1'),
        lambda: result_zip(mutate=lambda m, r, t, c: m.update(contract_version='3')),
        lambda: result_v3(events_doc(events__0__track_id=99)),
        lambda: result_v3(events_doc(events__0__recipient_track_id=1)),
        lambda: result_v3(events_doc(events__0__recipient_track_id=None)),
        lambda: result_v3(events_doc(events__1__success=True)),
        lambda: result_v3(events_doc(events__0__end_s=9.0)),
        lambda: result_v3(events_doc(events__0__start_s=500.0)),
        lambda: result_v3(events_doc(events__0__start_xy=[90.0, 5.0])),
        lambda: result_v3(events_doc(events__0__kind='shot')),
        lambda: result_v3(events_doc(kinds=['pass', 'shot'])),
        lambda: result_v3(events_doc(events__0__extra=1)),
        lambda: result_v3(events_doc(ball__frames_with_ball=1.5)),
        lambda: result_v3(events_doc(events__0__team='C')),
    ],
)
def test_contract_3_rejects_bad_events(raw):
    from aifootball.analytics.exchange import ExchangeError, validate_result

    with pytest.raises(ExchangeError):
        validate_result(raw())


SHOT = {'kind': 'shot', 'team': 'A', 'start_s': 12.0, 'on_target': True, 'confidence': 0.6}


def test_shot_candidates_ride_along_with_passes():
    from aifootball.analytics.exchange import validate_result

    raw = json.loads(events_doc())
    raw['candidates'] = [SHOT, {**SHOT, 'start_s': 40.0, 'team': 'B', 'on_target': None}]
    result = validate_result(result_v3(json.dumps(raw).encode()))
    # Кандидаты — подсказки разметки: не события и не статистика.
    assert [c['start_s'] for c in result.events['candidates']] == [12.0, 40.0]
    assert result.events['kinds'] == ['pass']


@pytest.mark.parametrize(
    'candidate',
    [
        {**SHOT, 'kind': 'pass'},
        {**SHOT, 'team': 'C'},
        {**SHOT, 'start_s': 500.0},
        {**SHOT, 'on_target': 'yes'},
        {**SHOT, 'confidence': 2.0},
        {**SHOT, 'extra': 1},
    ],
)
def test_bad_shot_candidates_are_rejected(candidate):
    from aifootball.analytics.exchange import ExchangeError, validate_result

    raw = json.loads(events_doc())
    raw['candidates'] = [candidate]
    with pytest.raises(ExchangeError):
        validate_result(result_v3(json.dumps(raw).encode()))


@pytest.mark.parametrize(
    'value,ok',
    [
        (base64.b64encode(bytes(range(156))).decode(), True),
        (base64.b64encode(bytes(155)).decode(), False),
        ('не base64', False),
        (42, False),
    ],
)
def test_fragment_appearance_is_156_bytes_of_base64(tmp_path, value, ok):
    from aifootball.analytics.exchange import ExchangeError, validate_result

    def mutate(m, r, t, c):
        t['tracks'][0]['appearance'] = value

    path = tmp_path / 'result.zip'
    path.write_bytes(result_zip(mutate=mutate))
    if ok:
        assert validate_result(path).tracks['tracks'][0]['appearance'] == value
    else:
        with pytest.raises(ExchangeError, match='признак внешности'):
            validate_result(path)


def test_appearance_size_matches_the_feature():
    from aifootball.analytics.exchange import APPEARANCE_BYTES
    from aifootball.perception.appearance import APPEARANCE_DIMS

    assert APPEARANCE_BYTES == APPEARANCE_DIMS


def _with_fragment(**change):
    def mutate(m, r, t, c):
        t['tracks'].append(
            {'track_id': 4, 'team': 'A', 'role': 'player', 'intervals': [[61, 70]], 'thumb': None, 'has_metrics': False}
        )
        fragment = {
            'track_id': 4,
            'team': 'A',
            'observed_s': 9.0,
            'distance_m': 20.0,
            'hsr_m': 0.0,
            'sprints': 0,
            'vmax_ms': None,
            'heatmap_cells': [[5, 5, 9.0]],
            **change,
        }
        r['periods'][0]['fragments'] = [fragment]

    return mutate


@pytest.mark.parametrize(
    'change,error',
    [
        ({}, None),
        ({'heatmap_cells': [[99, 5, 1.0]]}, 'тепловая карта фрагмента'),
        ({'team': 'B'}, 'Команда/роль фрагмента'),
        ({'distance_m': 1000.0}, 'Дистанция'),
        ({'track_id': 1}, 'повторный трек'),
    ],
)
def test_short_fragments_in_the_report_are_validated(tmp_path, change, error):
    from aifootball.analytics.exchange import ExchangeError, validate_result

    path = tmp_path / 'result.zip'
    path.write_bytes(result_zip(mutate=_with_fragment(**change)))
    if error is None:
        assert validate_result(path).report['periods'][0]['fragments'][0]['track_id'] == 4
    else:
        with pytest.raises(ExchangeError, match=error):
            validate_result(path)


@pytest.mark.parametrize('share,ok', [(0.4, True), (None, True), (1.5, False)])
def test_match_flow_in_the_report_is_validated(tmp_path, share, ok):
    from aifootball.analytics.exchange import ExchangeError, validate_result

    def mutate(m, r, t, c):
        team = {'observed_s': 50.0, 'attack_share': share}
        r['periods'][0]['flow'] = {
            'bin_s': 60,
            'bins': [{'half': 1, 'minute': 0, 'start_s': 0.0, 'A': team, 'B': team}],
        }

    path = tmp_path / 'result.zip'
    path.write_bytes(result_zip(mutate=mutate))
    if ok:
        assert validate_result(path).report['periods'][0]['flow']['bins'][0]['A']['attack_share'] == share
    else:
        with pytest.raises(ExchangeError, match='чужой трети'):
            validate_result(path)


def _board(goals, final=None):
    counted = {s: sum(g['side'] == s for g in goals) for s in ('left', 'right')}
    return {'source': 'broadcast', 'overlay': 'Мяч ТВ', 'final': final or counted, 'goals': goals}


GOAL = {'t_s': 5.0, 'side': 'left', 'period': 1, 'elapsed_s': 5.0}


@pytest.mark.parametrize(
    'board,error',
    [
        (_board([GOAL]), None),
        (_board([GOAL], final={'left': 2, 'right': 0}), 'Итог табло'),
        (_board([{**GOAL, 'side': 'home'}]), 'Неверный гол табло'),
        (_board([{**GOAL, 't_s': 1e6}]), 'время гола табло'),
        (_board([{**GOAL, 't_s': 8.0}, GOAL]), 'не по порядку'),
    ],
)
def test_scoreboard_in_the_report_is_validated(tmp_path, board, error):
    from aifootball.analytics.exchange import ExchangeError, validate_result

    def mutate(m, r, t, c):
        r['scoreboard'] = board

    path = tmp_path / 'result.zip'
    path.write_bytes(result_zip(mutate=mutate))
    if error is None:
        assert validate_result(path).report['scoreboard']['final'] == {'left': 1, 'right': 0}
    else:
        with pytest.raises(ExchangeError, match=error):
            validate_result(path)
