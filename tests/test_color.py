import math

import numpy as np

from aifootball.perception.color import torso_lab


def _frame_with_shirt(bgr):
    frame = np.full((200, 200, 3), 120, dtype=np.uint8)  # серый «пол»
    frame[40:100, 60:140] = bgr  # футболка
    return frame


def test_red_shirt_has_high_a():
    _, a, _ = torso_lab(_frame_with_shirt((0, 0, 255)), (50, 20, 150, 200))
    assert a > 170


def test_green_shirt_has_low_a():
    _, a, _ = torso_lab(_frame_with_shirt((0, 200, 0)), (50, 20, 150, 200))
    assert a < 90


def test_box_outside_frame_gives_nan():
    lab = torso_lab(np.zeros((100, 100, 3), np.uint8), (300, 300, 350, 400))
    assert all(math.isnan(v) for v in lab)
