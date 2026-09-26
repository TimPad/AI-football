import cv2
import numpy as np

from aifootball.geometry.undistort import undistort_points
from aifootball.venue import Calibration

K = np.array([[800.0, 0, 640], [0, 800.0, 360], [0, 0, 1]])


def _project(points_3d, dist):
    pixels, _ = cv2.projectPoints(points_3d, np.zeros(3), np.zeros(3), K, dist)
    return pixels.reshape(-1, 2)


def test_without_calibration_points_pass_through():
    points = np.array([[10.0, 20.0], [30.0, 40.0]])

    np.testing.assert_allclose(undistort_points(points, None), points)


def test_removes_barrel_distortion():
    dist = np.array([-0.3, 0.1, 0.0, 0.0, 0.0])
    points_3d = np.array([[0.5, 0.3, 1.0], [-0.6, -0.4, 1.0], [0.1, -0.2, 1.0]])
    distorted = _project(points_3d, dist)
    ideal = _project(points_3d, np.zeros(5))

    restored = undistort_points(distorted, Calibration(K=K, dist=dist))

    np.testing.assert_allclose(restored, ideal, atol=0.5)


def test_strong_wide_angle_distortion_at_frame_edge():
    # широкий угол камеры наблюдения (Ярославль): в углах кадра сжатие больше чем вдвое;
    # пяти итераций cv2.undistortPoints по умолчанию тут мало — ошибка сотни пикселей
    dist = np.array([1.29127, 0.27929, 0.0, 0.0, 0.00519, 1.75295, 0.66647, 0.04208])
    k = np.array([[1500.0, 0, 1296], [0, 1500.0, 972], [0, 0, 1]])
    points_3d = np.array([[-1.9, -0.9, 1.0], [1.5, 1.2, 1.0], [0.2, 0.1, 1.0]])
    distorted, _ = cv2.projectPoints(points_3d, np.zeros(3), np.zeros(3), k, dist)
    ideal, _ = cv2.projectPoints(points_3d, np.zeros(3), np.zeros(3), k, np.zeros(8))

    restored = undistort_points(distorted.reshape(-1, 2), Calibration(K=k, dist=dist))

    np.testing.assert_allclose(restored, ideal.reshape(-1, 2), atol=0.1)
