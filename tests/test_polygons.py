import numpy as np

from aifootball.geometry.polygons import points_in_polygon

SQUARE = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float32)


def test_inside_outside_and_boundary():
    points = np.array([[5, 5], [15, 5], [10, 5], [-1, -1]], dtype=np.float32)

    assert points_in_polygon(points, SQUARE).tolist() == [True, False, True, False]


def test_empty_input():
    assert points_in_polygon(np.zeros((0, 2)), SQUARE).shape == (0,)
