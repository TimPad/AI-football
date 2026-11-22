"""Обработчик задания с поворотной камерой: привязка к эталону до детекции, трекинг в плоскости эталона."""

import json
from hashlib import sha256
from zipfile import ZipFile

import cv2
import numpy as np
import pytest
import yaml

from aifootball import schemas
from aifootball.analytics.exchange import canonical
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


def ptz_job(path, reference, overlay=(), badge=None):
    """Задание поворотной камеры, как его выдаёт кабинет: тип камеры и графика в снимке и в venue.yaml,
    контура поля нет, эталонный кадр обязателен; плашка повтора (кадр, (x, y)) — по желанию."""
    with ZipFile(path) as source:
        files = {n: source.read(n) for n in source.namelist()}
    job = json.loads(files['job.json'])
    camera = job['context']['camera']
    camera.update(motion='ptz', overlay=[list(r) for r in overlay], polygon_px=None)
    cfg = yaml.safe_load(files['venue.yaml'])
    cfg['camera'] = {'motion': 'ptz', 'overlay': camera['overlay']}
    files.pop('pitch_polygon.json')
    if badge is not None:
        image, xy = badge
        raw = cv2.imencode('.png', image)[1].tobytes()
        camera['replay_badge'] = {
            'sha256': sha256(raw).hexdigest(),
            'xy': list(xy),
            'size': [image.shape[1], image.shape[0]],
        }
        cfg['camera']['replay_badge_xy'] = list(xy)
        files['replay_badge.png'] = raw
    job['context_hash'] = sha256(canonical(job['context'])).hexdigest()
    files['job.json'] = json.dumps(job).encode()
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


def rewrite(path, change):
    """Копия задания рядом с изменёнными файлами (change получает словарь «имя -> байты»)."""
    with ZipFile(path) as source:
        files = {n: source.read(n) for n in source.namelist()}
    change(files)
    out = path.with_name(f'tampered-{len(list(path.parent.glob("tampered-*")))}.zip')
    with ZipFile(out, 'w') as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return out


def edit_venue(change):
    def apply(files):
        cfg = yaml.safe_load(files['venue.yaml'])
        change(cfg)
        files['venue.yaml'] = yaml.safe_dump(cfg).encode()

    return apply


def edit_context(change):
    def apply(files):
        job = json.loads(files['job.json'])
        change(job['context']['camera'])
        job['context_hash'] = sha256(canonical(job['context'])).hexdigest()
        files['job.json'] = json.dumps(job).encode()

    return apply


BADGE_XY = (330, 160)


def badge_image():
    """Плашка повтора: шахматка 40 × 24 px, на сцене такой нет."""
    cells = (np.indices((3, 5)).sum(0) % 2 * 230 + 10).astype(np.uint8)
    return cv2.resize(cells, (40, 24), interpolation=cv2.INTER_NEAREST)


def test_read_job_checks_moving_camera_against_snapshot(cv_case):
    from aifootball.analytics.exchange import ExchangeError
    from aifootball.processor.job import read_job

    job, *_ = cv_case
    # Секция camera в venue.yaml при неподвижной камере в снимке — подмена.
    with pytest.raises(ExchangeError, match='CV-геометрия'):
        read_job(rewrite(job, edit_venue(lambda cfg: cfg.update(camera={'motion': 'ptz', 'overlay': []}))))
    ptz_job(job, crop(scene(), *REF_ORIGIN), overlay=[(0, 0, 1, 0.1)], badge=(badge_image(), BADGE_XY))
    camera = read_job(job).contract['context']['camera']
    assert camera['motion'] == 'ptz' and camera['polygon_px'] is None and camera['replay_badge']['xy'] == [330, 160]
    cases = {
        'Поворотная камера': [
            edit_venue(lambda cfg: cfg['camera'].update(overlay=[[0, 0, 1, 0.2]])),
            edit_venue(lambda cfg: cfg['camera'].update(replay_badge_xy=[0, 0])),
            edit_venue(lambda cfg: cfg.pop('camera')),
            lambda files: files.update({'pitch_polygon.json': b'{"points_px": [[0, 0], [9, 0], [9, 9]]}'}),
        ],
        'Плашка повтора': [lambda files: files.update({'replay_badge.png': b'not the badge'})],
        'Эталонный кадр': [lambda files: files.pop('reference.jpg')],
        'эталонный кадр профиля': [
            lambda files: (files.pop('reference.jpg'), edit_context(lambda c: c.pop('reference_sha256'))(files))
        ],
        'Неизвестный тип': [edit_context(lambda c: c.update(motion='drone'))],
    }
    for message, changes in cases.items():
        for change in changes:
            with pytest.raises(ExchangeError, match=message):
                read_job(rewrite(job, change))


def test_ptz_job_with_overlay_and_replay_badge_passes_process_job(cv_case, tmp_path):
    """Задание поворотной камеры, как его выдаёт кабинет, проходит process-job целиком: повтор по плашке
    в координаты не попадает, графика трансляции закрыта, результат принимается кабинетом."""
    from aifootball.analytics.exchange import validate_result
    from aifootball.processor.job import process_job

    job, _, models, _ = cv_case
    image = scene()
    badge = badge_image()
    video = tmp_path / 'broadcast.mp4'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter.fourcc(*'mp4v'), 2, (W, H))
    for n in range(130):
        frame = crop(image, *origin(n))
        if 90 <= n < 102:  # повтор: 6 с с плашкой
            x, y = BADGE_XY
            frame[y : y + badge.shape[0], x : x + badge.shape[1]] = badge[..., None]
        writer.write(frame)
    writer.release()
    ptz_job(job, crop(image, *REF_ORIGIN), overlay=[(0, 0, 0.25, 0.1)], badge=(badge, BADGE_XY))

    output = process_job(job, video, tmp_path / 'result.zip', models=models)
    result = validate_result(output)
    registration = result.checks['camera_registration']
    assert len(registration['replays']) == 1
    start, end = registration['replays'][0]
    assert 44 <= start <= 45.5 and 50.5 <= end <= 52  # 45–51 с и запас 0,5 с по краям
    assert registration['share']['ok'] > 0.85
    assert any('Камера поворотная' in w for w in result.checks['warnings'])
