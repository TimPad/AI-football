import polars as pl
import pytest

from aifootball import schemas
from aifootball.analytics.validation import (
    evaluate_detections,
    evaluate_projection_error,
    evaluate_tracking,
)


def test_evaluate_detections_perfect_match():
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

    res = evaluate_detections(df, df)

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


def test_evaluate_projection_error():
    gt = pl.DataFrame({
        "frame_id": [1, 2],
        "track_id": [1, 1],
        "x_m": [10.0, 20.0],
        "y_m": [2.0, 10.0],  # y_m=2.0 (дальняя), y_m=10.0 (ближняя при width_m=15.0)
    })
    # Предсказание со смещением 1.0 м
    pred = pl.DataFrame({
        "frame_id": [1, 2],
        "track_id": [1, 1],
        "x_m": [11.0, 20.0],
        "y_m": [2.0, 11.0],
    })

    res = evaluate_projection_error(pred, gt, width_m=15.0)

    assert res["mae_m"] == pytest.approx(1.0, abs=1e-2)
    assert res["near_half_mae_m"] == pytest.approx(1.0, abs=1e-2)
    assert res["far_half_mae_m"] == pytest.approx(1.0, abs=1e-2)
