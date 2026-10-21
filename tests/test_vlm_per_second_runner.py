from hashlib import sha256
import importlib.util
from pathlib import Path

import pytest

from aifootball.understanding.per_second_pilot import VERSION
from test_joint_vlm_pilot import Client


def runner(monkeypatch):
    scripts = Path(__file__).parents[1] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location('per_second_runner', scripts / 'verify_per_second_vlm.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest(tmp_path, *, windows=2):
    video = tmp_path / 'source.mp4'
    video.write_bytes(b'synthetic-video')
    cv = tmp_path / 'cv'
    cv.mkdir()
    for name in ('tracks.parquet', 'state.parquet', 'detections.parquet', 'meta.json'):
        (cv / name).write_bytes(name.encode())
    return {'cases': [{'id': 'case1', 'video': str(video), 'cv': str(cv), 'venue': str(tmp_path / 'venue'),
                       'start_ms': 0, 'end_ms': windows * 12000}]}


def prepare(case, begin, end, variant, output):
    from aifootball.understanding.types import MediaAsset, Window
    kind = 'full' if variant == 'fullframe' else 'follow'
    folder = output / 'media' / case['id'] / f'{begin}' / kind
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'clip.mp4'
    path.write_bytes(f'synthetic-{begin}-{kind}'.encode())
    media = MediaAsset('clip', 'video', path, sha256(path.read_bytes()).hexdigest(), begin, end, False)
    crop = None if kind == 'full' else {'size': [1296, 972], 'keys': [[0.0, 0, 0]]}
    hints = [{'t': 0, 'players_speed_p80_m_s': 1.0}] if variant == 'follow_cv' else None
    return Window(f'w{begin}{kind}', begin, end, (), media, (1,), 'native'), crop, hints


def answer():
    return {'schema_version': VERSION, 'ball_in_play': ['playing'] * 11 + ['stoppage'], 'shots': []}


def fail(*args, **kwargs):
    raise AssertionError('rebuilt a frozen plan')


def test_dry_run_prepares_every_variant_without_network(monkeypatch, tmp_path):
    m = runner(monkeypatch)
    client = Client(answer())
    reports = m.run(manifest(tmp_path), tmp_path / 'out', client=client, prepare=prepare)
    assert client.calls == 0 and set(reports) == {'fullframe', 'follow', 'follow_cv'}
    assert all(w['status'] == 'dry_run' for r in reports.values() for w in r['cases'][0]['windows'])
    assert all((tmp_path / 'out' / v / 'report.json').exists() for v in reports)


def test_each_variant_window_is_paid_once_then_replayed_from_frozen_plan(monkeypatch, tmp_path):
    m = runner(monkeypatch)
    inputs, client, out = manifest(tmp_path), Client(answer()), tmp_path / 'out'
    first = m.run(inputs, out, apply=True, client=client, prepare=prepare)
    assert client.calls == 6 and first['follow']['new_requests_this_run'] == 6
    second = m.run(inputs, out, cache_only=True, client=client, prepare=fail)
    assert client.calls == 6 and second['follow']['new_requests_this_run'] == 0
    window = second['follow_cv']['cases'][0]['windows'][1]
    assert window['status'] == 'valid' and window['cache_hit'] is True and window['crop']['size'] == [1296, 972]
    assert window['projected_document']['states'][-1] == {'kind': 'stoppage', 'start_ms': 11000, 'end_ms': 12000}


def test_invalid_answer_is_kept_but_not_scored(monkeypatch, tmp_path):
    m = runner(monkeypatch)
    reports = m.run(manifest(tmp_path, windows=1), tmp_path / 'out', apply=True,
                    client=Client({'ball_in_play': ['playing'] * 3}), prepare=prepare)
    window = reports['fullframe']['cases'][0]['windows'][0]
    assert window['status'] == 'invalid_response' and window['document'] == {'ball_in_play': ['playing'] * 3}
    assert 'projected_document' not in window


def test_plan_larger_than_approved_budget_stops_before_network(monkeypatch, tmp_path):
    m = runner(monkeypatch)
    client = Client(answer())
    with pytest.raises(ValueError, match='limit'):
        m.run(manifest(tmp_path, windows=31), tmp_path / 'out', apply=True, client=client, prepare=prepare)
    assert client.calls == 0
