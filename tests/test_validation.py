import numpy as np
import polars as pl
import pytest

from aifootball import schemas
from aifootball.geometry.homography import apply_homography
from aifootball.analytics.validation import (
    evaluate_detections,
    evaluate_projection_error,
    evaluate_tracking,
)
from aifootball.venue import load_venue
from conftest import make_venue_dir


def test_evaluate_detections_perfect_match(tmp_path):
    df = pl.DataFrame({
        "frame_id": [1, 1, 2],
        "ts": [0.1, 0.1, 0.2],
        "cls": ["person", "person", "person"],
        "x1": [10.0, 50.0, 10.0],
        "y1": [10.0, 100.0, 10.0],
        "x2": [30.0, 70.0, 30.0],
        "y2": [40.0, 150.0, 40.0],
        "conf": [0.9, 0.9, 0.9],
        "torso_l": [120.0, 120.0, 120.0],
        "torso_a": [60.0, 60.0, 60.0],
        "torso_b": [140.0, 140.0, 140.0],
    })

    res = evaluate_detections(df, df, _perspective_venue(tmp_path, near_y0=True))

    assert res["precision"] == 1.0
    assert res["recall"] == 1.0
    assert res["f1"] == 1.0
    assert res["near_half"]["f1"] == 1.0
    assert res["far_half"]["f1"] == 1.0


def test_evaluate_tracking_id_swaps():
    gt = pl.DataFrame({
        "frame_id": [1, 2, 3],
        "track_id": [100, 100, 100],
    })
    # В детекции предсказанный ID сменился с 1 на 2 (ID swap)
    pred = pl.DataFrame({
        "frame_id": [1, 2, 3],
        "track_id": [1, 1, 2],
    })

    res = evaluate_tracking(pred, gt)

    assert res["id_swaps"] == 1
    assert res["mota"] > 0.0


def test_evaluate_projection_error(tmp_path):
    gt = pl.DataFrame({
        "frame_id": [1, 2],
        "track_id": [1, 1],
        "x_m": [10.0, 20.0],
        "y_m": [2.0, 18.0],  # у камеры и у дальнего края
    })
    # Предсказание со смещением 1.0 м
    pred = pl.DataFrame({
        "frame_id": [1, 2],
        "track_id": [1, 1],
        "x_m": [11.0, 20.0],
        "y_m": [2.0, 19.0],
    })

    res = evaluate_projection_error(pred, gt, _perspective_venue(tmp_path, near_y0=True))

    assert res["mae_m"] == pytest.approx(1.0, abs=1e-2)
    assert res["near_half_mae_m"] == pytest.approx(1.0, abs=1e-2)
    assert res["far_half_mae_m"] == pytest.approx(1.0, abs=1e-2)


def _perspective_venue(root, near_y0: bool):
    """Поле 40x20, камера у края y=0 (near_y0) или у края y=20: там поле в кадре крупнее."""
    to_px = np.array([[40.0, 0, 0], [0, 40.0, 0], [0, 0.1, 1.0]])
    if not near_y0:
        to_px = to_px @ np.array([[1.0, 0, 0], [0, -1.0, 20.0], [0, 0, 1.0]])
    corners = apply_homography(to_px, np.array([[0, 0], [40, 0], [40, 20], [0, 20]], float))
    return load_venue(make_venue_dir(root, polygon=corners.tolist(), H=np.linalg.inv(to_px).tolist()))


@pytest.mark.parametrize("near_y0", [True, False])
def test_projection_error_halves_follow_camera(tmp_path, near_y0):
    # у камеры ошибка 0.1 м, у дальнего края 1.0 м — какой край ближний, решает гомография
    near_y, far_y = (2.0, 18.0) if near_y0 else (18.0, 2.0)
    gt = pl.DataFrame({"frame_id": [1, 2], "track_id": [1, 1], "x_m": [20.0, 20.0], "y_m": [near_y, far_y]})
    pred = gt.with_columns(x_m=pl.Series([20.1, 21.0]))

    res = evaluate_projection_error(pred, gt, _perspective_venue(tmp_path, near_y0))

    assert res["near_half_mae_m"] == pytest.approx(0.1, abs=1e-3)
    assert res["far_half_mae_m"] == pytest.approx(1.0, abs=1e-3)


@pytest.mark.parametrize("near_y0", [True, False])
def test_detection_halves_follow_camera(tmp_path, near_y0):
    venue = _perspective_venue(tmp_path, near_y0)
    to_px = np.linalg.inv(venue.H)
    near_y, far_y = (2.0, 18.0) if near_y0 else (18.0, 2.0)
    foot_near, foot_far = apply_homography(to_px, np.array([[20.0, near_y], [20.0, far_y]]))

    def box(foot, h):
        return [foot[0] - h / 4, foot[1] - h, foot[0] + h / 4, foot[1]]

    gt = _person_boxes([1, 1], [box(foot_near, 60), box(foot_far, 20)])
    pred = _person_boxes([1], [box(foot_near, 60)])  # дальнего игрока детектор пропустил

    res = evaluate_detections(pred, gt, venue)

    assert res["near_half"]["recall"] == 1.0
    assert res["far_half"]["recall"] == 0.0


def _person_boxes(frames, boxes):
    n = len(frames)
    return pl.DataFrame({
        "frame_id": frames,
        "ts": [0.1] * n,
        "cls": ["person"] * n,
        "x1": [b[0] for b in boxes],
        "y1": [b[1] for b in boxes],
        "x2": [b[2] for b in boxes],
        "y2": [b[3] for b in boxes],
        "conf": [0.9] * n,
        "torso_l": [120.0] * n,
        "torso_a": [60.0] * n,
        "torso_b": [140.0] * n,
    })