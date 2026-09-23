"""Снятие дисторсии объектива с точек (не с кадров целиком — так дешевле)."""

import cv2
import numpy as np

from aifootball.venue import Calibration


def undistort_points(points: np.ndarray, calib: Calibration | None) -> np.ndarray:
    """Пиксели исходного кадра -> пиксели идеальной камеры без дисторсии.

    Без калибровки точки возвращаются как есть: для установок со слабой
    дисторсией (Кострома) калибровка не нужна.
    """
    points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if calib is None or len(points) == 0:
        return points
    undistorted = cv2.undistortPoints(points.reshape(-1, 1, 2), calib.K, calib.dist, P=calib.K)
    return undistorted.reshape(-1, 2)
