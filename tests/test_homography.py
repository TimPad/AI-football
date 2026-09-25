import numpy as np
import pytest

from aifootball.geometry.homography import apply_homography, fit_homography, leave_one_out_error, pixels_per_meter

# Настоящая перспектива: не просто масштаб, а наклон плоскости.
TRUE_H = np.array([[0.05, 0.01, -3.0], [0.002, 0.08, -10.0], [0.0001, 0.0009, 1.0]])
PIXELS = np.array([[100, 400], [1100, 420], [900, 250], [300, 240], [640, 330], [200, 320]], float)


def test_recovers_known_homography():
    meters = apply_homography(TRUE_H, PIXELS)

    H, error = fit_homography(PIXELS, meters)

    assert error < 1e-6
    np.testing.assert_allclose(apply_homography(H, PIXELS), meters, atol=1e-6)


def test_needs_four_points():
    with pytest.raises(ValueError, match="минимум 4"):
        fit_homography(PIXELS[:3], PIXELS[:3])


def test_leave_one_out_catches_bad_point():
    meters = apply_homography(TRUE_H, PIXELS)
    assert leave_one_out_error(PIXELS, meters) < 1e-6

    meters[4] += [2.0, 0.0]  # одна точка размечена с ошибкой в 2 м

    assert leave_one_out_error(PIXELS, meters) > 0.3


def test_empty_points():
    assert apply_homography(TRUE_H, np.zeros((0, 2))).shape == (0, 2)


def test_pixels_per_meter():
    # пиксели -> метры: 10 px = 1 м везде
    H = np.diag([0.1, 0.1, 1.0])
    np.testing.assert_allclose(pixels_per_meter(H, np.array([[0.0, 0.0], [30.0, 12.0]])), [10.0, 10.0], rtol=1e-4)

    # перспектива: чем больше y в метрах, тем мельче поле в кадре
    to_px = np.array([[40.0, 0, 0], [0, 40.0, 0], [0, 0.1, 1.0]])
    near, far = pixels_per_meter(np.linalg.inv(to_px), np.array([[0.0, 0.0], [0.0, 15.0]]))
    assert near == pytest.approx(40.0, rel=1e-3)
    assert far < near / 2
