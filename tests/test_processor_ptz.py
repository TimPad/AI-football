"""Обработчик задания с поворотной камерой: привязка к эталону до детекции, трекинг в плоскости эталона."""

import json
from zipfile import ZipFile

import cv2
import numpy as np
import pytest
import yaml

from aifootball import schemas
from test_processor_camera import with_reference
from test_processor_resume import Predictor, cv_case  # noqa: F401  (фикстура)

W, H = 400, 200
SCENE = (1200, 600)
REF_ORIGIN = (400, 200)  # левый верхний угол эталона на сцене: пиксели эталона = пиксели сцены - REF_ORIGIN


def scene(seed=11):
    rng = np.random.default_rng(seed)
    image = cv2.resize(rng.integers(40, 215, (30, 60), dtype=np.uint8), SCENE, interpolation=cv2.INTER_NEAREST)
    for _ in range(500):
        center = tuple(int(v) for v in rng.integers(0, SCENE))
        cv2.circle(image, center, int(rng.integers(3, 10)), int(rng.integers(0, 255)), -1)
    return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)


def origin(n):
    """Куда смотрит камера в кадре n: медленный пан вокруг эталона."""
    return REF_ORIGIN[0] + 60 * np.sin(n / 12), REF_ORIGIN[1] + 25 * np.cos(n / 15)


def crop(image, x, y):
    return cv2.warpAffine(image, np.float32([[1, 0, -x], [0, 1, -y]]), (W, H), flags=cv2.INTER_LINEAR)


def ptz_job(path, reference):
    with ZipFile(path) as source:
        files = {n: source.read(n) for n in source.namelist()}
    cfg = yaml.safe_load(files['venue.yaml'])
    cfg['camera'] = {'motion': 'ptz'}
    files['venue.yaml'] = yaml.safe_dump(cfg).encode()
    with ZipFile(path, 'w') as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return with_reference(path, reference)


@pytest.fixture
def ptz_case(cv_case, tmp_path):
    job, _, models, ws = cv_case
    image = scene()
    ptz_job(job, crop(image, *REF_ORIGIN))
    video = tmp_path / 'pan.mp4'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter.fourcc(*'mp4v'), 2, (W, H))
    for n in range(130):
        writer.write(crop(image, *origin(n)))
    writer.release()
    return job, video, models, ws


def test_ptz_job_registers_frames_and_tracks_in_reference_pixels(ptz_case, monkeypatch):
    from aifootball.geometry import registration
    from aifootball.processor.cv import run_cv

    job, video, models, ws = ptz_case
    root = run_cv(job, video, ws('ptz'), models=models)
    meta = json.loads((root / 'meta.json').read_text())
    assert meta['camera_registration']['share']['ok'] > 0.95 and meta['camera_alignment'] is None
    reg = schemas.read(root / 'registration.parquet', 'registration')
    tracks = schemas.read(root / 'tracks.parquet', 'tracks')
    # Детектор видит игрока в одном и том же месте кадра, но камера панорамирует: рамки остаются
    # в пикселях кадра (для вырезок), а точка ног в пикселях эталона повторяет пан.
    assert tracks['track_id'].n_unique() == 1 and (tracks['x1'] == 80).all()
    joined = tracks.join(reg.select('frame_id', 'ts'), on='frame_id')
    expected = 92.5 + np.array([origin(round(t * 2))[0] for t in joined['ts'].to_list()]) - REF_ORIGIN[0]
    assert np.abs(joined['foot_x'].to_numpy() - expected).max() < 1.5
    state = schemas.read(root / 'state.parquet', 'state')
    assert np.ptp(state['x_m'].to_numpy()) > 10  # 120 px пана = 12 м при 10 px/м

    calls = []
    monkeypatch.setattr(registration, 'register_video', lambda *a, **k: calls.append(1))
    run_cv(job, video, ws('ptz'), models=models)
    assert not calls  # готовая привязка не пересчитывается


def test_ptz_job_with_ball_model_or_foreign_reference_stops_before_detection(ptz_case):
    from aifootball.processor.cv import run_cv

    job, video, models, ws = ptz_case
    with pytest.raises(ValueError, match='мяча'):
        run_cv(job, video, ws('ball'), models=models, ball_model='ball/best.pt')
    unrelated = np.random.default_rng(5).integers(0, 255, (H, W, 3), dtype=np.uint8)
    with_reference(job, unrelated)  # эталон другой съёмки: ни один вид записи с ним не сверяется
    Predictor.calls = 0
    with pytest.raises(ValueError, match='не сверяется'):
        run_cv(job, video, ws('foreign'), models=models)
    assert Predictor.calls == 0  # часы детекции не потрачены


def test_registration_messages_warn_and_block_poor_coverage():
    from aifootball.geometry.registration import registration_messages

    good = {'share': {'ok': 0.93, 'weak': 0.02, 'lost': 0.03, 'replay': 0.02}, 'replays': [[10.0, 20.0]]}
    warnings, errors = registration_messages(good)
    assert errors == [] and '93%' in warnings[0] and '1, 10 с' in warnings[0]
    poor = {**good, 'share': {**good['share'], 'ok': 0.3}}
    assert registration_messages(poor)[1]
    assert registration_messages(None) == ([], [])


def test_track_without_registration_file_explains_the_missing_step(tmp_path):
    from aifootball.cli import read_registration
    from aifootball.venue import load_venue
    from test_registration import ptz_venue

    venue = load_venue(ptz_venue(tmp_path))
    with pytest.raises(FileNotFoundError, match='register'):
        read_registration(tmp_path, venue)
