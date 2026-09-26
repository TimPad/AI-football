import math
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

from aifootball.perception.detect import BALL, PERSON, boxes_to_rows

FRAME = np.zeros((100, 100, 3), dtype=np.uint8)


def _rows(classes, confs):
    xyxy = np.array([[10, 10, 30, 60]] * len(classes), dtype=np.float32)
    return boxes_to_rows(5, 0.5, FRAME, xyxy, np.array(classes), np.array(confs), 0.25, 0.10)


def test_each_class_has_own_threshold():
    rows = _rows([PERSON, PERSON, BALL, BALL], [0.9, 0.15, 0.15, 0.05])

    assert [(r["cls"], r["conf"]) for r in rows] == [("person", 0.9), ("ball", 0.15)]


def test_other_classes_dropped():
    assert _rows([2], [0.99]) == []  # 'car'


def test_person_gets_torso_color_ball_does_not():
    person, ball = _rows([PERSON, BALL], [0.9, 0.5])

    assert not math.isnan(person["torso_l"])
    assert math.isnan(ball["torso_l"])
    assert (person["frame_id"], person["ts"]) == (5, 0.5)


class _Arr:
    def __init__(self, a):
        self.a = np.asarray(a, dtype=float)

    def cpu(self):
        return self

    def numpy(self):
        return self.a


class _FakeYOLO:
    calls: list = []

    def __init__(self, weights):
        pass

    def predict(self, frames, **kwargs):
        _FakeYOLO.calls.append(kwargs)
        empty = SimpleNamespace(xyxy=_Arr(np.zeros((0, 4))), cls=_Arr([]), conf=_Arr([]))
        return [SimpleNamespace(boxes=empty) for _ in frames]


def test_detect_video_takes_ball_from_own_detector(monkeypatch, tmp_path, venue, tiny_video):
    import ultralytics

    from aifootball.perception.detect import detect_video

    monkeypatch.setattr(ultralytics, "YOLO", _FakeYOLO)
    weights = tmp_path / "w.pt"
    weights.write_bytes(b"")
    _FakeYOLO.calls.clear()

    def ball_detector(frame):
        return np.array([[10.0, 10.0, 20.0, 20.0]]), np.array([0.7])

    det = detect_video(tiny_video, venue, weights, ball_detector=ball_detector)

    assert all(call["classes"] == [0] for call in _FakeYOLO.calls)  # общая модель — только люди
    balls = det.filter(pl.col("cls") == "ball")
    assert balls.height == det["frame_id"].n_unique() == 20  # 50 кадров 25 fps -> 20 при 10 fps
    assert balls["conf"].to_list() == pytest.approx([0.7] * 20)
