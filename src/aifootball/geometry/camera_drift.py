"""Сверка положения неподвижной камеры с эталонным кадром профиля и поправка геометрии.

Между днями камеру могут чуть повернуть или задеть: старая гомография тогда ошибается на метры в
дальней половине (сдвиг 10 px — до 1.7 м на Ярославле). Стены, трибуны и разметка неподвижны, поэтому
сдвиг находится сопоставлением фона кадра с эталоном. Поворот камеры в выпрямленных (без дисторсии)
координатах — точная гомография, поэтому поправка считается там; смещение крепления на сантиметры
при расстоянии до трибун в десятки метров даёт пренебрежимый параллакс.
"""
from dataclasses import dataclass

import cv2
import numpy as np

from aifootball.geometry.undistort import undistort_points

MAX_SIDE_PX = 1600          # кадр уменьшается для поиска особых точек: быстрее, точность — доли пикселя после пересчёта
MIN_INLIERS = 40            # меньше совпавших точек фона — сверке не верим
STILL_PX = 2.0              # контур сместился меньше — камера на месте, геометрия не трогается
MAX_SHIFT_FRAC = 0.1        # контур сместился больше 10% ширины кадра — это другая установка, нужна новая калибровка
CONSISTENT_PX = 4.0         # оценки по времени расходятся больше — камеру сдвинули во время записи
SAMPLE_EVERY_S = 60.0


@dataclass(frozen=True)
class Estimate:
    H: np.ndarray            # выпрямленные пиксели текущего кадра -> выпрямленные пиксели эталона
    inliers: int
    matches: int


def distort_points(points, calib):
    """Выпрямленные пиксели -> пиксели исходного кадра (обратно к undistort_points)."""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if calib is None or len(points) == 0:
        return points
    normalized = cv2.undistortPoints(points.reshape(-1, 1, 2), calib.K, None).reshape(-1, 2)
    rays = np.column_stack([normalized, np.ones(len(normalized))])
    projected, _ = cv2.projectPoints(rays, np.zeros(3), np.zeros(3), calib.K, calib.dist)
    return projected.reshape(-1, 2)


def _gray(image, scale):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    return cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray


def estimate(reference, current, calib=None) -> Estimate | None:
    """Гомография текущего кадра к эталону по особым точкам фона; игроки отсеиваются RANSAC."""
    scale = min(1.0, MAX_SIDE_PX / max(reference.shape[:2]))
    sift = cv2.SIFT_create(4000)
    k1, d1 = sift.detectAndCompute(_gray(reference, scale), None)
    k2, d2 = sift.detectAndCompute(_gray(current, scale), None)
    if d1 is None or d2 is None or len(k1) < MIN_INLIERS or len(k2) < MIN_INLIERS:
        return None
    pairs = cv2.BFMatcher().knnMatch(d2, d1, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
    if len(good) < MIN_INLIERS:
        return None
    cur = undistort_points(np.float64([k2[m.queryIdx].pt for m in good]) / scale, calib)
    ref = undistort_points(np.float64([k1[m.trainIdx].pt for m in good]) / scale, calib)
    H, mask = cv2.findHomography(cur, ref, cv2.RANSAC, 3.0)  # отбор точек фона: игроки и блики отсеиваются
    if H is None or mask is None or int(mask.sum()) < MIN_INLIERS:
        return None
    inl = mask.ravel().astype(bool)
    if calib is None:
        # Без модели объектива — подобие (сдвиг, поворот, масштаб): 4 параметра вместо 8.
        A, keep = cv2.estimateAffinePartial2D(cur[inl], ref[inl], method=cv2.LMEDS)
        if A is None:
            return None
        return Estimate(np.vstack([A, [0, 0, 1]]), int(keep.sum()), len(good))
    # С объективом — только поворот камеры: 3 параметра, хорошо переносится с трибун на ближнюю часть поля.
    for _ in range(2):
        R = _rotation(cur[inl], ref[inl], calib.K)
        Hr = calib.K @ R @ np.linalg.inv(calib.K)
        residual = np.hypot(*(cv2.perspectiveTransform(cur.reshape(-1, 1, 2), Hr).reshape(-1, 2) - ref).T)
        inl = residual < 3.0
        if inl.sum() < MIN_INLIERS:
            return None
    return Estimate(Hr / Hr[2, 2], int(inl.sum()), len(good))


def _rotation(cur, ref, K):
    """Поворот камеры по парам точек (Кабш): лучи текущего кадра -> лучи эталона."""
    Ki = np.linalg.inv(K)
    rays = lambda pts: (lambda r: r / np.linalg.norm(r, axis=1, keepdims=True))((Ki @ np.column_stack([pts, np.ones(len(pts))]).T).T)
    a, b = rays(cur), rays(ref)
    U, _, Vt = np.linalg.svd(a.T @ b)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    return Vt.T @ np.diag([1.0, 1.0, d]) @ U.T


def polygon_shift_px(est: Estimate, venue) -> float:
    """Насколько сместился контур поля на кадре (максимум по вершинам)."""
    polygon = np.asarray(venue.pitch_polygon_px, dtype=np.float64)
    moved = corrected_polygon(est, venue)
    return float(np.hypot(*(moved - polygon).T).max())


def corrected_polygon(est: Estimate, venue) -> np.ndarray:
    ideal = undistort_points(np.asarray(venue.pitch_polygon_px, dtype=np.float64), venue.calib)
    pts = cv2.perspectiveTransform(ideal.reshape(-1, 1, 2), np.linalg.inv(est.H)).reshape(-1, 2)
    return distort_points(pts, venue.calib)


def corrected_homography(est: Estimate, venue) -> np.ndarray:
    """Метры из выпрямленных пикселей текущего кадра: сначала к эталону, потом прежняя гомография."""
    H = venue.H @ est.H
    return H / H[2, 2]


def error_if_uncorrected_m(est: Estimate, venue, step_m: float = 1.0) -> tuple[float, float]:
    """Ошибка координат (медиана, максимум, м) по сетке площадки, если читать сдвинутый кадр старой геометрией."""
    xs, ys = np.meshgrid(np.arange(0, venue.length_m + 1e-9, step_m), np.arange(0, venue.width_m + 1e-9, step_m))
    meters = np.column_stack([xs.ravel(), ys.ravel()])
    ref_px = cv2.perspectiveTransform(meters.reshape(-1, 1, 2), np.linalg.inv(venue.H)).reshape(-1, 2)
    cur_px = cv2.perspectiveTransform(ref_px.reshape(-1, 1, 2), np.linalg.inv(est.H)).reshape(-1, 2)
    read = cv2.perspectiveTransform(cur_px.reshape(-1, 1, 2), venue.H).reshape(-1, 2)
    err = np.hypot(*(read - meters).T)
    return float(np.median(err)), float(err.max())


def read_frame(video, t_s):
    cap = cv2.VideoCapture(str(video))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, t_s * 1000)
        ok, frame = cap.read()
        return frame if ok else None
    finally:
        cap.release()


def check_camera(video, reference, venue, duration_s: float, every_s: float = SAMPLE_EVERY_S) -> dict:
    """Сверка начала записи и затем раз в every_s с эталоном. Решение и поправленная геометрия — в словаре.

    status: unchanged — камера на месте; corrected — сдвиг найден и учтён; unverified — фон не сопоставился;
    too_large — сдвиг больше допустимого (нужна новая калибровка); moved — камеру сдвинули во время записи.
    """
    times = list(np.arange(min(5.0, duration_s / 2), max(duration_s - 1.0, 0.0) + 1e-9, every_s))[:120] or [0.0]
    samples, found = [], []
    for t in times:
        frame = read_frame(video, float(t))
        est = estimate(reference, frame, venue.calib) if frame is not None else None
        shift = polygon_shift_px(est, venue) if est else None
        samples.append({'t_s': round(float(t), 1), 'inliers': est.inliers if est else 0,
                        'shift_px': None if shift is None else round(shift, 1)})
        if est:
            found.append((float(t), est, shift))
    out = {'samples': samples, 'reference_checked': len(found)}
    if not found:
        return {**out, 'status': 'unverified'}
    # Сдвиг между соседними оценками: сравниваем, где окажется контур поля по каждой из них.
    polygons = [corrected_polygon(est, venue) for _, est, _ in found]
    for (t, _, _), a, b in zip(found[1:], polygons, polygons[1:]):
        if float(np.hypot(*(b - a).T).max()) > CONSISTENT_PX:
            return {**out, 'status': 'moved', 'moved_at_s': round(t, 1)}
    t, best, shift = max(found, key=lambda item: item[1].inliers)
    median_m, max_m = error_if_uncorrected_m(best, venue)
    out.update(shift_px=round(shift, 1), error_if_uncorrected_m={'median': round(median_m, 2), 'max': round(max_m, 2)})
    if shift > MAX_SHIFT_FRAC * reference.shape[1]:
        return {**out, 'status': 'too_large'}
    if shift < STILL_PX:
        return {**out, 'status': 'unchanged'}
    return {**out, 'status': 'corrected', 'homography': corrected_homography(best, venue).tolist(),
            'polygon_px': [[round(float(x), 2), round(float(y), 2)] for x, y in corrected_polygon(best, venue)]}


def alignment_messages(alignment: dict | None) -> tuple[list[str], list[str]]:
    """Предупреждения и критические ошибки проверок качества по итогам сверки камеры."""
    if not alignment:
        return [], []
    status = alignment['status']
    error = (alignment.get('error_if_uncorrected_m') or {}).get('max')
    if status == 'corrected':
        return [f"Камера сдвинута относительно калибровки на {alignment['shift_px']:.0f} px (без поправки ошибка до {error:.1f} м); "
                'геометрия поправлена автоматически'], []
    if status == 'unverified':
        return ['Не удалось сверить положение камеры с эталонным кадром: использована калибровка профиля как есть'], []
    if status == 'too_large':
        return [], [f"Камера сдвинута на {alignment['shift_px']:.0f} px относительно калибровки: создайте новую версию профиля камеры"]
    if status == 'moved':
        moved = alignment['moved_at_s']
        return [], [f'Камеру сдвинули во время записи (около {int(moved // 60)}:{int(moved % 60):02d}): '
                    'координаты после сдвига неверны, нужна новая калибровка или обработка частями']
    return [], []


def apply_alignment(venue, alignment: dict | None):
    """Установка с поправленной геометрией, если сдвиг найден и учтён."""
    if not alignment or alignment.get('status') != 'corrected':
        return venue
    from dataclasses import replace
    return replace(venue, H=np.asarray(alignment['homography'], dtype=np.float64),
                   pitch_polygon_px=np.asarray(alignment['polygon_px'], dtype=np.float64))
