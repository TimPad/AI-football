import math

import numpy as np

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
