"""Проверка «точка внутри контура» — фильтр детекций по зоне поля."""

import cv2
import numpy as np


def points_in_polygon(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    """True для точек внутри многоугольника или на его границе.

    points: (N, 2), polygon: (M, 2) — в одной системе координат.
    """
    if len(points) == 0:
        return np.zeros(0, dtype=bool)
    contour = np.asarray(polygon, dtype=np.float32).reshape(-1, 1, 2)
    return np.array(
        [cv2.pointPolygonTest(contour, (float(x), float(y)), False) >= 0 for x, y in points],
        dtype=bool,
    )
