import numpy as np

from aifootball.geometry.polygons import is_simple_polygon, points_in_polygon, points_near_polygon

SQUARE = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float32)


def test_inside_outside_and_boundary():
    points = np.array([[5, 5], [15, 5], [10, 5], [-1, -1]], dtype=np.float32)

    assert points_in_polygon(points, SQUARE).tolist() == [True, False, True, False]


def test_empty_input():
    assert points_in_polygon(np.zeros((0, 2)), SQUARE).shape == (0,)


def test_simple_polygons():
    assert is_simple_polygon(SQUARE)
    assert is_simple_polygon([[0, 0], [10, 0], [5, 8]])
    # невыпуклый, но без самопересечений
    assert is_simple_polygon([[0, 0], [10, 0], [10, 10], [5, 3], [0, 10]])


def test_self_intersecting_polygon_detected():
    bow_tie = [[0, 0], [10, 10], [10, 0], [0, 10]]
    assert not is_simple_polygon(bow_tie)


def test_real_misordered_markup():
    # Разметка Костромы, где вершины 6 и 7 поставлены не по порядку обхода
    clicked = [[8, 521], [355, 462], [743, 387], [1157, 409], [1023, 716], [2, 662], [339, 714]]
    assert not is_simple_polygon(clicked)
    fixed = clicked[:5] + [clicked[6], clicked[5]]
    assert is_simple_polygon(fixed)


def test_points_near_polygon_with_margin():
    square = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], np.float32)
    pts = np.array([[50, 50], [105, 50], [130, 50]], float)

    assert points_near_polygon(pts, square, margin_px=0).tolist() == [True, False, False]
    assert points_near_polygon(pts, square, margin_px=10).tolist() == [True, True, False]
