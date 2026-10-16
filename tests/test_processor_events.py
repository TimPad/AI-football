"""Передачи по мячу в пакете результата: events.json и контракт версии 3."""
import json
import numpy as np
import polars as pl
import pytest
from conftest import write_video
from report_fixtures import synthetic_match
from test_processor_job import job_package
from aifootball import schemas

FPS = 15
PLAYERS = [(1, 'A', 10.0, 10.0), (2, 'A', 24.0, 10.0), (3, 'B', 30.0, 4.0), (4, 'B', 30.0, 16.0)]


def _state(seconds):
    rows = [{'frame_id': k, 'ts': float(t), 'track_id': tid, 'role': 'player', 'team': team, 'x_m': x, 'y_m': y,
             'vx': 0.0, 'vy': 0.0, 'speed': 0.0, 'interpolated': False}
            for tid, team, x, y in PLAYERS for k, t in enumerate(np.arange(0, seconds, 1 / FPS))]
    return pl.DataFrame(rows, schema=schemas.STATE)


def _detections(seconds, ball_at):
    """По человеку в каждом кадре (кадр обработан) и мяч там, где ball_at(t) не None; 10 px = 1 м, мяч на полу — низ бокса."""
    rows = []
    for k, t in enumerate(np.arange(0, seconds, 1 / FPS)):
        rows.append({'frame_id': k, 'ts': float(t), 'cls': 'person', 'x1': 95.0, 'y1': 70.0, 'x2': 105.0, 'y2': 100.0, 'conf': 0.9})
        p = ball_at(t)
        if p is not None:
            px, py = p[0] * 10, p[1] * 10
            rows.append({'frame_id': k, 'ts': float(t), 'cls': 'ball', 'x1': px - 3, 'y1': py - 6, 'x2': px + 3, 'y2': py, 'conf': 0.9})
    return pl.DataFrame(rows).with_columns(torso_l=pl.lit(None, pl.Float32), torso_a=pl.lit(None, pl.Float32),
                                           torso_b=pl.lit(None, pl.Float32)).cast(schemas.DETECTIONS)


def _pass(t):
    """0–2 с у игрока 1, 2–4 с катится к игроку 2 (7 м/с — медленнее удара), 4–6 с у игрока 2."""
    if t < 2: return (10.3, 10.0)
    if t < 4: return (10.3 + 6.7 * (t - 2), 10.0)
    return (23.7, 10.0)


def _artifacts(tmp_path, ball_at, seconds=6, fps=15, meta=True):
    work = tmp_path / 'artifacts'; work.mkdir(exist_ok=True)
    schemas.write(_detections(seconds, ball_at), work / 'detections.parquet', 'detections')
    if meta:
        (work / 'meta.json').write_text(json.dumps({'ball_model': 'ball/best.pt', 'ball_model_sha256': 'c' * 64, 'target_fps': fps}))
    return work


def test_pass_between_teammates_goes_to_events(venue, tmp_path):
    from aifootball.processor.job import ball_events
    events, warning = ball_events(_artifacts(tmp_path, _pass), venue, _state(6), [(0.0, 6.0)], {1, 2, 3, 4})
    assert warning is None
    assert events['kinds'] == ['pass'] and events['ball'] == {'model': 'ball/best.pt', 'sha256': 'c' * 64, 'frames_with_ball': 1.0}
    [passed] = events['events']
    assert (passed['track_id'], passed['recipient_track_id'], passed['team'], passed['success']) == (1, 2, 'A', True)
    assert passed['start_s'] < passed['end_s'] and passed['start_xy'] == [10.0, 10.0] and passed['end_xy'] == [24.0, 10.0]


@pytest.mark.parametrize('case,expected', [
    ('rare_ball', 'мяч найден лишь в 17%'),
    ('slow_fps', 'не реже 15 кадров/с'),
])
def test_events_are_withheld_with_a_reason(venue, tmp_path, case, expected):
    from aifootball.processor.job import ball_events
    ball_at = (lambda t: _pass(t) if t < 1 else None) if case == 'rare_ball' else _pass
    work = _artifacts(tmp_path, ball_at, fps=10 if case == 'slow_fps' else 15)
    events, warning = ball_events(work, venue, _state(6), [(0.0, 6.0)], {1, 2, 3, 4})
    assert events is None and expected in warning


def test_no_ball_model_means_no_events(venue, tmp_path):
    from aifootball.processor.job import ball_events
    assert ball_events(_artifacts(tmp_path, _pass, meta=False), venue, _state(6), [(0.0, 6.0)], {1, 2}) == (None, None)


def test_ball_model_name_stays_inside_the_models_folder(tmp_path):
    from aifootball.processor.job import ball_model_path
    from aifootball.analytics.exchange import ExchangeError
    (tmp_path / 'hall').mkdir(); (tmp_path / 'hall' / 'best.pt').write_bytes(b'w')
    assert ball_model_path(tmp_path, 'hall/best.pt') == tmp_path / 'hall' / 'best.pt'
    for name in ['../best.pt', '/abs/best.pt', 'a/b/c/best.pt', 'hall/best.onnx', 'hall/missing.pt']:
        with pytest.raises(ExchangeError):
            ball_model_path(tmp_path, name)


def test_package_with_ball_is_contract_3(venue, tmp_path):
    from aifootball.processor.job import package_result
    from aifootball.analytics.exchange import validate_result
    path, _ = job_package(venue, tmp_path)
    video = write_video(tmp_path / 'clip.mp4', n_frames=140, fps=2, size=(400, 200))
    state, tracks = synthetic_match(seconds=65, sprint=False)
    work = tmp_path / 'artifacts'
    schemas.write(state, work / 'state.parquet', 'state'); schemas.write(tracks, work / 'tracks.parquet', 'tracks')
    # Мяч всё время у ног игрока 11: передач нет, но пакет с мячом — версия 3
    holder = state.filter(pl.col('track_id') == 11).sort('ts')
    owner = dict(zip(holder['ts'].to_list(), zip(holder['x_m'].to_list(), holder['y_m'].to_list())))
    rows = [{'frame_id': int(round(t * 2)), 'ts': t, 'cls': c, 'x1': x * 10 - 3, 'y1': y * 10 - 6, 'x2': x * 10 + 3, 'y2': y * 10, 'conf': 0.9}
            for t, (x, y) in owner.items() for c in ('person', 'ball')]
    detections = pl.DataFrame(rows).with_columns(torso_l=pl.lit(None, pl.Float32), torso_a=pl.lit(None, pl.Float32),
                                                 torso_b=pl.lit(None, pl.Float32)).cast(schemas.DETECTIONS)
    schemas.write(detections, work / 'detections.parquet', 'detections')
    (work / 'meta.json').write_text(json.dumps({'ball_model': 'ball/best.pt', 'ball_model_sha256': 'c' * 64, 'target_fps': 15}))
    result = validate_result(package_result(path, video, work, tmp_path / 'result.zip'))
    assert result.manifest['contract_version'] == '3' and result.manifest['processor']['ball_model'] == 'ball/best.pt'
    assert result.events['kinds'] == ['pass'] and result.events['events'] == []
    assert result.understanding is None


def test_ball_model_uses_measured_confidence_and_margin(venue):
    from dataclasses import replace
    from aifootball.processor.job import ball_settings
    tuned = ball_settings(replace(venue, conf_ball=0.1, ball_margin_px=0), 2592)
    assert tuned.conf_ball == 0.25 and tuned.ball_margin_px == 80
    # Заданные в установке значения не перекрываются
    assert ball_settings(replace(venue, conf_ball=0.4, ball_margin_px=30), 2592).ball_margin_px == 30
