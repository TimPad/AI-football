"""Цвет формы игрока — признак для разделения на команды."""

import math

import cv2
import numpy as np

NAN3 = (math.nan, math.nan, math.nan)


def torso_lab(frame: np.ndarray, box) -> tuple[float, float, float]:
    """Медианный цвет торса в Lab (шкала OpenCV 0..255).

    Берём центральную часть верхней половины бокса: там футболка, а по краям
    бокса — пол и соседние игроки. Медиана устойчива к номеру и полосам на форме.
    """
    x1, y1, x2, y2 = (float(v) for v in box)
    w, h = x2 - x1, y2 - y1
    top, bottom = int(y1 + 0.2 * h), int(y1 + 0.5 * h)
    left, right = int(x1 + 0.3 * w), int(x1 + 0.7 * w)

    frame_h, frame_w = frame.shape[:2]
    top, bottom = max(top, 0), min(bottom, frame_h)
    left, right = max(left, 0), min(right, frame_w)
    if bottom <= top or right <= left:
        return NAN3

    crop = frame[top:bottom, left:right]
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3)
    median = np.median(lab, axis=0)
    return float(median[0]), float(median[1]), float(median[2])
