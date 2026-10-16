"""Сверка положения камеры с эталонным кадром: сдвиг находится по фону и учитывается в геометрии."""
import cv2
import numpy as np
import pytest
from conftest import SCALE_H, make_venue_dir

from aifootball.venue import Calibration, load_venue
from aifootball.geometry import camera_drift as D

W, H = 640, 480
POLYGON = [[40, 40], [600, 40], [600, 440], [40, 440]]


def scene(seed=1):
    """Неподвижный «зал» с деталями: блоки разной яркости и круги — особые точки для SIFT."""
    rng = np.random.default_rng(seed)
    image = cv2.resize(rng.integers(0, 255, (30, 40), dtype=np.uint8), (W, H), interpolation=cv2.INTER_NEAREST)
    for _ in range(60):
        cv2.circle(image, tuple(int(v) for v in rng.integers(0, [W, H])), int(rng.integers(4, 18)), int(rng.integers(0, 255)), -1)
    return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)


def shifted(image, dx, dy):
    return cv2.warpAffine(image, np.float32([[1, 0, dx], [0, 1, dy]]), (W, H), borderMode=cv2.BORDER_REFLECT)


def video(path, frames, fps=2):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*'mp4v'), fps, (W, H))
    for frame in frames: writer.write(frame)
    writer.release()
    return path


@pytest.fixture
def venue(tmp_path):
    return load_venue(make_venue_dir(tmp_path / 'venue', polygon=POLYGON, H=SCALE_H))


def test_camera_in_place_keeps_the_geometry(venue, tmp_path):
    ref = scene()
    result = D.check_camera(video(tmp_path / 'v.mp4', [ref] * 20), ref, venue, 10, every_s=3)
    assert result['status'] == 'unchanged' and result['shift_px'] < D.STILL_PX
    assert D.apply_alignment(venue, result) is venue and D.alignment_messages(result) == ([], [])


def test_small_shift_is_found_and_corrected(venue, tmp_path):
    ref = scene()
    result = D.check_camera(video(tmp_path / 'v.mp4', [shifted(ref, 12, 8)] * 20), ref, venue, 10, every_s=3)
    assert result['status'] == 'corrected' and result['shift_px'] == pytest.approx(np.hypot(12, 8), abs=1.0)
    assert np.allclose(result['polygon_px'], np.array(POLYGON) + [12, 8], atol=1.0)
    aligned = D.apply_alignment(venue, result)
    # Точка поля, снятая сдвинутой камерой, читается в тех же метрах, что и до сдвига
    meters = cv2.perspectiveTransform(np.float64([[[312 + 12, 208 + 8]]]), aligned.H).ravel()
    assert meters == pytest.approx([31.2, 20.8], abs=0.1)
    warnings, errors = D.alignment_messages(result)
    assert 'поправлена автоматически' in warnings[0] and errors == []


def test_too_large_shift_and_movement_during_recording_are_critical(venue, tmp_path):
    ref = scene()
    large = D.check_camera(video(tmp_path / 'a.mp4', [shifted(ref, 90, 0)] * 20), ref, venue, 10, every_s=3)
    assert large['status'] == 'too_large' and 'новую версию профиля' in D.alignment_messages(large)[1][0]
    # 20 с записи, камеру толкнули на 10-й секунде; сверки в 5, 8, 11, 14, 17 с
    moved = D.check_camera(video(tmp_path / 'b.mp4', [ref] * 20 + [shifted(ref, 15, 0)] * 20), ref, venue, 20, every_s=3)
    assert moved['status'] == 'moved' and moved['moved_at_s'] == 11
    assert 'во время записи' in D.alignment_messages(moved)[1][0]


def test_featureless_frame_is_unverified_not_blocking(venue, tmp_path):
    flat = np.full((H, W, 3), 128, np.uint8)
    result = D.check_camera(video(tmp_path / 'v.mp4', [flat] * 10), scene(), venue, 5, every_s=2)
    assert result['status'] == 'unverified'
    warnings, errors = D.alignment_messages(result)
    assert errors == [] and 'как есть' in warnings[0]


def test_lens_model_estimates_a_camera_rotation(tmp_path):
    K = np.array([[500.0, 0, W / 2], [0, 500.0, H / 2], [0, 0, 1]])
    calib = Calibration(K, np.zeros(5))
    R = cv2.Rodrigues(np.deg2rad([0.6, -0.8, 0.3]))[0]
    turned = K @ R @ np.linalg.inv(K)      # пиксели эталона -> пиксели повёрнутой камеры
    ref = scene(2)
    cur = cv2.warpPerspective(ref, turned, (W, H), borderMode=cv2.BORDER_REFLECT)
    est = D.estimate(ref, cur, calib)
    points = np.float64([[100, 100], [320, 240], [560, 400]])
    moved = cv2.perspectiveTransform(points.reshape(-1, 1, 2), turned)
    back = cv2.perspectiveTransform(moved, est.H).reshape(-1, 2)
    assert np.abs(back - points).max() < 0.5


def test_distort_inverts_undistort():
    from aifootball.geometry.undistort import undistort_points
    calib = Calibration(np.array([[800.0, 0, 640], [0, 800.0, 360], [0, 0, 1]]), np.array([-0.2, 0.05, 0, 0, 0]))
    raw = np.float64([[10, 20], [640, 360], [1200, 700]])
    assert np.abs(D.distort_points(undistort_points(raw, calib), calib) - raw).max() < 0.01
