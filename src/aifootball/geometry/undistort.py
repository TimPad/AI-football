"""Снятие дисторсии объектива с точек (не с кадров целиком — так дешевле)."""

import cv2
import numpy as np

from aifootball.venue import Calibration

UNDISTORT_CRITERIA = (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 200, 1e-6)


def undistort_points(points: np.ndarray, calib: Calibration | None) -> np.ndarray:
    """Пиксели исходного кадра -> пиксели идеальной камеры без дисторсии.

    Без калибровки точки возвращаются как есть: для установок со слабой
    дисторсией (Кострома) калибровка не нужна.
    """
    points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if calib is None or len(points) == 0:
        return points
    # Обратное искажение ищется итерациями. Пяти итераций cv2.undistortPoints по умолчанию
    # хватает для слабой дисторсии, но у широкоугольной камеры (сжатие в углах в 2 раза)
    # ошибка у краёв кадра — сотни пикселей. Итераций — до сходимости.
    undistorted = cv2.undistortImagePoints(points.reshape(-1, 1, 2), calib.K, calib.dist, None, UNDISTORT_CRITERIA)
    return undistorted.reshape(-1, 2)
