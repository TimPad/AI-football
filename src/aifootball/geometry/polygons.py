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


def is_simple_polygon(polygon) -> bool:
    """True, если стороны многоугольника не пересекают друг друга.

    Самопересекающийся контур («бантик») получается, если при разметке
    поставить вершины не по порядку обхода. Для такого контура проверка
    «точка внутри» даёт бессмысленный ответ.
    """
    points = np.asarray(polygon, dtype=float).reshape(-1, 2)
    n = len(points)
    if n < 3:
        return False
    edges = [(points[i], points[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # первая и последняя стороны соседние: делят вершину
            if _segments_cross(*edges[i], *edges[j]):
                return False
    return True


def _segments_cross(p1, p2, q1, q2) -> bool:
    """Отрезки p1p2 и q1q2 пересекаются во внутренней точке."""

    def side(a, b, c):
        return np.sign((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))

    return side(q1, q2, p1) * side(q1, q2, p2) < 0 and side(p1, p2, q1) * side(p1, p2, q2) < 0
