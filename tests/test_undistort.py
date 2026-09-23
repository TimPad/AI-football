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
