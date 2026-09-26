import numpy as np
import polars as pl
import pytest

from aifootball import schemas
from aifootball.analytics.validation import ball_size_px, evaluate_ball
from aifootball.venue import load_venue
from conftest import SCALE_H, make_venue_dir

FIELD = [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]


def _labels(rows):
    """rows: (frame_id, status, x, y)."""
    return pl.DataFrame(
        {
            "frame_id": [r[0] for r in rows],
            "ts": [r[0] / 25 for r in rows],
            "status": [r[1] for r in rows],
            "x": [r[2] for r in rows],
            "y": [r[3] for r in rows],
        },
        schema=schemas.BALL_LABELS,
    )


def _balls(rows):
    """rows: (frame_id, x1, y1, x2, y2, conf)."""
    n = len(rows)
    return pl.DataFrame(
        {
            "frame_id": [r[0] for r in rows],
            "ts": [r[0] / 25 for r in rows],
            "cls": ["ball"] * n,
            "x1": [r[1] for r in rows],
            "y1": [r[2] for r in rows],
            "x2": [r[3] for r in rows],
            "y2": [r[4] for r in rows],
            "conf": [r[5] for r in rows],
            "torso_l": [np.nan] * n,
            "torso_a": [np.nan] * n,
            "torso_b": [np.nan] * n,
        },
        schema=schemas.DETECTIONS,
    )


@pytest.fixture
def venue(tmp_path):
    return load_venue(make_venue_dir(tmp_path / "v", polygon=FIELD, H=SCALE_H))


def test_evaluate_ball_counts_hits_misses_and_false_alarms(venue):
    labels = _labels([
        (1, "visible", 100.0, 100.0),  # найден
        (2, "visible", 200.0, 200.0),  # детекция мимо
        (3, "visible", 300.0, 300.0),  # детекции нет
        (4, "absent", None, None),     # ложное срабатывание
        (5, "absent", None, None),
        (6, "hidden", None, None),     # не считается ни туда, ни сюда
    ])
    dets = _balls([
        (1, 95, 95, 105, 105, 0.5),
        (2, 400, 400, 410, 410, 0.5),
        (4, 50, 50, 58, 58, 0.5),
        (6, 70, 70, 78, 78, 0.5),
        (9, 10, 10, 18, 18, 0.5),  # кадр без метки
    ])

    res = evaluate_ball(dets, labels, venue, conf_min=0.1)

    assert res["visible"] == 3 and res["found"] == 1
    assert res["recall"] == pytest.approx(1 / 3, abs=1e-3)
    assert res["absent"] == 2 and res["false_alarm_frames"] == 1
    assert res["false_alarm_rate"] == 0.5
    assert res["hidden"] == 1
    # кадры с детекцией среди visible+absent: 1 (верно), 2 и 4 (неверно)
    assert res["precision"] == pytest.approx(1 / 3, abs=1e-3)


def test_evaluate_ball_tolerates_click_next_to_small_box(venue):
    labels = _labels([(1, "visible", 103.0, 100.0)])
    dets = _balls([(1, 95, 95, 100, 105, 0.5)])  # клик на 3 px правее бокса

    assert evaluate_ball(dets, labels, venue, conf_min=0.1)["found"] == 1


def test_evaluate_ball_applies_conf_threshold(venue):
    labels = _labels([(1, "visible", 100.0, 100.0)])
    dets = _balls([(1, 95, 95, 105, 105, 0.05)])

    assert evaluate_ball(dets, labels, venue, conf_min=0.1)["found"] == 0
    assert evaluate_ball(dets, labels, venue, conf_min=0.01)["found"] == 1


def test_evaluate_ball_ignores_detections_outside_pitch(venue):
    labels = _labels([(1, "absent", None, None)])
    dets = _balls([(1, 1500, 1500, 1508, 1508, 0.9)])

    assert evaluate_ball(dets, labels, venue, conf_min=0.1)["false_alarm_frames"] == 0


def test_precision_uses_top_detection_of_frame(venue):
    # Две детекции: самая уверенная — ложная. Дальше по пайплайну пойдёт именно она
    labels = _labels([(1, "visible", 100.0, 100.0)])
    dets = _balls([(1, 95, 95, 105, 105, 0.3), (1, 500, 500, 508, 508, 0.8)])

    res = evaluate_ball(dets, labels, venue, conf_min=0.1)

    assert res["found"] == 1
    assert res["precision"] == 0.0


def test_ball_size_px_from_homography(tmp_path):
    # SCALE_H: 10 px = 1 м, мяч 0.2 м -> 2 px; H в 5 раз мельче -> 50 px/м -> 10 px
    coarse = load_venue(make_venue_dir(tmp_path / "a", polygon=FIELD, H=SCALE_H))
    fine_h = (np.array(SCALE_H) @ np.diag([0.2, 0.2, 1.0])).tolist()
    fine = load_venue(make_venue_dir(tmp_path / "b", polygon=FIELD, H=fine_h))
    pts = np.array([[100.0, 100.0], [500.0, 800.0]])

    np.testing.assert_allclose(ball_size_px(pts, coarse), [2.0, 2.0], rtol=1e-3)
    np.testing.assert_allclose(ball_size_px(pts, fine), [10.0, 10.0], rtol=1e-3)


def test_evaluate_ball_splits_recall_by_ball_size(venue):
    labels = _labels([(1, "visible", 100.0, 100.0), (2, "visible", 200.0, 200.0)])
    dets = _balls([(1, 95, 95, 105, 105, 0.5)])

    by_size = evaluate_ball(dets, labels, venue, conf_min=0.1)["by_size"]

    # при SCALE_H мяч 2 px — все метки в самой мелкой группе
    assert by_size["<6px"] == {"visible": 2, "found": 1, "recall": 0.5}
    assert by_size["6-10px"]["visible"] == 0


def test_evaluate_ball_without_homography_skips_size_split(tmp_path):
    # до гомографии площадки размер мяча не посчитать, но recall и ложные — можно
    venue = load_venue(make_venue_dir(tmp_path / "v", polygon=FIELD))
    labels = _labels([(1, "visible", 100.0, 100.0), (2, "absent", None, None)])
    dets = _balls([(1, 95, 95, 105, 105, 0.5)])

    res = evaluate_ball(dets, labels, venue, conf_min=0.1)

    assert res["found"] == 1 and res["false_alarm_frames"] == 0
    assert res["by_size"] is None


def test_evaluate_ball_uses_venue_ball_margin(tmp_path):
    # мяч в 10 px за линией (аут): при запасе 20 px детекция засчитывается, без запаса — отброшена
    labels = _labels([(1, "visible", 1010.0, 500.0)])
    dets = _balls([(1, 1005, 495, 1015, 505, 0.9)])
    strict = load_venue(make_venue_dir(tmp_path / "a", polygon=FIELD, H=SCALE_H))
    loose = load_venue(make_venue_dir(tmp_path / "b", polygon=FIELD, H=SCALE_H, processing={"ball_margin_px": 20}))

    assert evaluate_ball(dets, labels, strict, conf_min=0.1)["found"] == 0
    assert evaluate_ball(dets, labels, loose, conf_min=0.1)["found"] == 1
