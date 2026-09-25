"""Гомография «пиксели пола -> метры на поле»."""

import cv2
import numpy as np

MIN_POINTS = 4


def fit_homography(px: np.ndarray, m: np.ndarray) -> tuple[np.ndarray, float]:
    """Считает H по парам точек. Возвращает H и среднюю ошибку на этих же точках, м."""
    px = np.asarray(px, dtype=np.float64).reshape(-1, 2)
    m = np.asarray(m, dtype=np.float64).reshape(-1, 2)
    if len(px) != len(m):
        raise ValueError(f"разное число точек: {len(px)} пикселей и {len(m)} метров")
    if len(px) < MIN_POINTS:
        raise ValueError(f"нужно минимум {MIN_POINTS} точки, дано {len(px)}")
    H, _ = cv2.findHomography(px, m, 0)
    if H is None:
        raise ValueError("точки вырождены (например, три на одной прямой): гомография не считается")
    return H, _mean_error(H, px, m)


def apply_homography(H: np.ndarray, points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(points) == 0:
        return points
    return cv2.perspectiveTransform(points.reshape(-1, 1, 2), H).reshape(-1, 2)


def pixels_per_meter(H: np.ndarray, points_m: np.ndarray, step_m: float = 0.1) -> np.ndarray:
    """Масштаб кадра в точках поля: сколько пикселей занимает метр.

    Берётся наибольший масштаб по направлениям (старшее сингулярное число якобиана
    «метры -> пиксели»): вдоль луча зрения пол сплющен, поперёк — нет. Чем ближе
    точка к камере, тем он больше.
    """
    points_m = np.asarray(points_m, dtype=np.float64).reshape(-1, 2)
    if len(points_m) == 0:
        return np.zeros(0)
    to_px = np.linalg.inv(H)
    base = apply_homography(to_px, points_m)
    along_x = (apply_homography(to_px, points_m + [step_m, 0.0]) - base) / step_m
    along_y = (apply_homography(to_px, points_m + [0.0, step_m]) - base) / step_m
    jacobians = np.stack([along_x, along_y], axis=2)
    return np.linalg.svd(jacobians, compute_uv=False)[:, 0]


def leave_one_out_error(px: np.ndarray, m: np.ndarray) -> float:
    """Честная ошибка: каждая точка проверяется гомографией, посчитанной без неё.

    Ошибка на тех же точках, по которым считали H, всегда занижена — при четырёх
    точках она просто ноль. Нужно минимум 5 точек.
    """
    px = np.asarray(px, dtype=np.float64).reshape(-1, 2)
    m = np.asarray(m, dtype=np.float64).reshape(-1, 2)
    if len(px) <= MIN_POINTS:
        raise ValueError(f"для проверки нужно больше {MIN_POINTS} точек, дано {len(px)}")
    errors = []
    for i in range(len(px)):
        rest = np.arange(len(px)) != i
        H, _ = fit_homography(px[rest], m[rest])
        errors.append(np.linalg.norm(apply_homography(H, px[i : i + 1])[0] - m[i]))
    return float(np.mean(errors))


def _mean_error(H: np.ndarray, px: np.ndarray, m: np.ndarray) -> float:
    return float(np.mean(np.linalg.norm(apply_homography(H, px) - m, axis=1)))
