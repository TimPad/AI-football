"""L1: детекция мяча дообученной моделью — по закрашенному кадру, вырезками в полном разрешении.

Мяч в кадре 5 Мп занимает 12–20 px; ужми кадр до 1280 — станет 6–10 px, и модель его не видит.
Поэтому кадр режется на перекрывающиеся вырезки tile x tile без масштабирования. Всё дальше
запаса за контуром поля закрашивается серым так же, как при обучении (tools.ball_dataset):
иначе модель находит запасные мячи у скамейки.

Поворотная камера трансляции видит каждый раз другую часть поля, поэтому зона поиска у неё задана на плоскости
поля в метрах и пересчитывается на каждый кадр по его привязке к эталону (PtzBallDetector).
"""

from collections.abc import Callable, Iterable
from pathlib import Path

import cv2
import numpy as np

FILL_BGR = (114, 114, 114)  # серый, которым YOLO сам заполняет поля при letterbox
MERGE_IOU = 0.3  # один мяч на стыке двух вырезок

# Поворотная камера. Закрыта только сторона за ближней к камере линией: там скамейки, запасные мячи и зрители
# (ВШЭ: скамейки сразу за бровкой). Остальные стороны открыты далеко: мяч в воздухе (удар над перекладиной, навес)
# на плоскости пола проецируется далеко за линии — полная маска поля скрывала 12 из 198 подписанных мячей ВШЭ.
PTZ_NEAR_MARGIN_M = 1.5
PTZ_FAR_M = 60.0
PTZ_HORIZON = 0.05  # точки плоскости с глубиной меньше этой доли глубины центра кадра — у «горизонта» камеры
PTZ_CLIP_PX = 4000  # проекция дальних точек плоскости обрезается прямоугольником с таким запасом вокруг кадра
PTZ_SEARCH = 'ptz-near-side-v1'  # входит в отпечаток обработки: смена зоны поиска не смешивается с сохранённой

# predict(вырезки) -> для каждой вырезки (боксы xyxy в её координатах, уверенности)
Predict = Callable[[list[np.ndarray]], list[tuple[np.ndarray, np.ndarray]]]


def _no_boxes() -> tuple[np.ndarray, np.ndarray]:
    return np.zeros((0, 4)), np.zeros(0)


def pitch_keep_mask(shape: tuple[int, int], polygon: np.ndarray, margin_px: int) -> np.ndarray:
    """255 — поле и запас margin_px вокруг него, 0 — то, что закрашивается."""
    keep = np.zeros(shape, np.uint8)
    cv2.fillPoly(keep, [np.round(polygon).astype(np.int32).reshape(-1, 1, 2)], 255)
    if margin_px > 0:
        keep = cv2.dilate(keep, np.ones((2 * margin_px + 1, 2 * margin_px + 1), np.uint8))
    return keep


def mask_outside_pitch(frame: np.ndarray, polygon: np.ndarray, margin_px: int) -> np.ndarray:
    out = frame.copy()
    out[pitch_keep_mask(frame.shape[:2], polygon, margin_px) == 0] = FILL_BGR
    return out


def cover_tiles(box: tuple[int, int, int, int], tile: int, width: int, height: int) -> list[tuple[int, int]]:
    """Углы вырезок tile x tile, покрывающих box = (x1, y1, x2, y2) с перекрытием, в пределах кадра."""
    x1, y1, x2, y2 = box

    def origins(lo: int, hi: int, size: int) -> list[int]:
        if size <= tile:  # кадр меньше вырезки: одна вырезка от края, детектор дополнит её сам
            return [0]
        n = max(1, int(np.ceil((hi - lo) / tile)))
        start, stop = max(0, lo), min(size - tile, hi - tile)
        if n == 1 or stop <= start:
            return [int(min(max(start, 0), size - tile))]
        return [int(round(v)) for v in np.linspace(start, stop, n)]

    return [(x0, y0) for y0 in origins(y1, y2, height) for x0 in origins(x1, x2, width)]


def merge_tile_boxes(boxes: np.ndarray, confs: np.ndarray, iou: float = MERGE_IOU) -> tuple[np.ndarray, np.ndarray]:
    """Склеивает дубли одного мяча из соседних вырезок: остаётся самый уверенный бокс."""
    order = np.argsort(-confs)
    kept: list[int] = []
    for i in order:
        if all(_iou(boxes[i], boxes[j]) < iou for j in kept):
            kept.append(i)
    return boxes[kept].reshape(-1, 4), confs[kept]


def detect_ball_in_frame(
    frame: np.ndarray, keep: np.ndarray, tiles: list[tuple[int, int]], tile: int, predict: Predict
) -> tuple[np.ndarray, np.ndarray]:
    """Боксы мяча (xyxy в координатах кадра) и уверенности на одном кадре."""
    masked = frame.copy()
    masked[keep == 0] = FILL_BGR
    crops = [masked[y0 : y0 + tile, x0 : x0 + tile] for x0, y0 in tiles]
    all_boxes, all_confs = [], []
    for (x0, y0), (boxes, confs) in zip(tiles, predict(crops)):
        if len(boxes):
            all_boxes.append(np.asarray(boxes, float) + [x0, y0, x0, y0])
            all_confs.append(np.asarray(confs, float))
    if not all_boxes:
        return _no_boxes()
    return merge_tile_boxes(np.vstack(all_boxes), np.concatenate(all_confs))


def yolo_predict(weights: Path, tile: int, conf: float, device: str) -> Predict:
    """Модель мяча YOLO на вырезках tile x tile без масштабирования."""
    from ultralytics import YOLO  # тяжёлый импорт — только когда реально детектируем

    if not weights.exists():
        raise FileNotFoundError(f'нет весов модели мяча: {weights}')
    model = YOLO(str(weights))

    def predict(crops: list[np.ndarray]) -> list[tuple[np.ndarray, np.ndarray]]:
        results = model.predict(crops, imgsz=tile, device=device, conf=conf, verbose=False)
        return [(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()) for r in results]

    return predict


class BallDetector:
    """Дообученная модель мяча, настроенная на кадр определённого размера и установку."""

    def __init__(
        self,
        weights: Path,
        polygon: np.ndarray,
        frame_shape: tuple[int, int],
        tile: int,
        margin_px: int,
        conf: float,
        device: str,
    ):
        self.predict = yolo_predict(weights, tile, conf, device)
        self.tile = tile
        height, width = frame_shape
        self.keep = pitch_keep_mask(frame_shape, polygon, margin_px)
        ys, xs = np.nonzero(self.keep)
        self.tiles = cover_tiles(
            (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1), tile, width, height
        )

    def __call__(self, frame: np.ndarray, frame_id: int | None = None) -> tuple[np.ndarray, np.ndarray]:
        return detect_ball_in_frame(frame, self.keep, self.tiles, self.tile, self.predict)


def clip_halfplane(poly: np.ndarray, g: Callable[[np.ndarray], float]) -> np.ndarray:
    """Сазерленд–Ходжмен: часть выпуклого многоугольника, где линейная функция g >= 0."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        ga, gb = g(a), g(b)
        if ga >= 0:
            out.append(a)
        if (ga >= 0) != (gb >= 0):
            out.append(a + (b - a) * ga / (ga - gb))
    return np.array(out, float).reshape(-1, 2)


def ptz_search_region_m(
    H: np.ndarray, length_m: float, width_m: float, near_margin_m: float = PTZ_NEAR_MARGIN_M
) -> np.ndarray:
    """Зона поиска мяча на плоскости поля (углы в метрах): за ближней к камере линией — near_margin_m,
    за остальными — PTZ_FAR_M. Ближняя — та, середина которой ниже всех на эталоне (H — пиксели эталона -> метры)."""
    L, W = length_m, width_m
    sides = np.array([[L / 2, 0.0, 1.0], [L, W / 2, 1.0], [L / 2, W, 1.0], [0.0, W / 2, 1.0]])  # y=0, x=L, y=W, x=0
    p = np.linalg.inv(H) @ sides.T
    near = int(np.argmax(p[1] / p[2]))
    lo, hi = [-PTZ_FAR_M, -PTZ_FAR_M], [L + PTZ_FAR_M, W + PTZ_FAR_M]
    if near == 0:
        lo[1] = -near_margin_m
    elif near == 1:
        hi[0] = L + near_margin_m
    elif near == 2:
        hi[1] = W + near_margin_m
    else:
        lo[0] = -near_margin_m
    return np.array([[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]], float)


def frame_keep_mask(
    frame_to_m: np.ndarray, region_m: np.ndarray, shape: tuple[int, int], overlay_keep: np.ndarray | None = None
) -> np.ndarray:
    """255 — где искать мяч на кадре поворотной камеры: зона region_m (метры) в этом кадре без графики трансляции.

    frame_to_m — гомография пикселей кадра в метры. Камера у середины поля, глядя на одни ворота, видит дальний
    конец поля «за горизонтом»: там проекция плоскости переворачивается и угол поля попадает на другую сторону
    кадра. Поэтому зона обрезается по глубине ещё в метрах, потом проецируется и только потом обрезается
    прямоугольником вокруг кадра. Обрезать координаты по отдельности нельзя: это искажает стороны многоугольника.
    """
    h, w = shape
    M = np.linalg.inv(frame_to_m)  # метры -> пиксели кадра
    c = frame_to_m @ [w / 2, h / 2, 1.0]
    depth = float(M[2] @ (c / c[2]))  # глубина центра кадра; знак гомографии произволен
    sign, limit = np.sign(depth), PTZ_HORIZON * abs(depth)
    poly = clip_halfplane(region_m, lambda q: sign * (M[2] @ [q[0], q[1], 1.0]) - limit)
    keep = np.zeros(shape, np.uint8)
    if len(poly) < 3:
        return keep
    p = np.column_stack([poly, np.ones(len(poly))]) @ M.T
    poly = p[:, :2] / p[:, 2:3]
    for k, lim, s in ((0, -PTZ_CLIP_PX, 1), (0, w + PTZ_CLIP_PX, -1), (1, -PTZ_CLIP_PX, 1), (1, h + PTZ_CLIP_PX, -1)):
        poly = clip_halfplane(poly, lambda q, k=k, lim=lim, s=s: s * (q[k] - lim))
    if len(poly) < 3:
        return keep
    cv2.fillPoly(keep, [np.round(poly).astype(np.int32).reshape(-1, 1, 2)], 255)
    return keep if overlay_keep is None else cv2.bitwise_and(keep, overlay_keep)


class PtzBallDetector:
    """Своя модель мяча на поворотной камере: зона поиска пересчитывается на каждый кадр по его привязке к эталону.

    Кадр без привязки (повтор, графика на весь экран, потерянный вид) пропускается: его рамки всё равно не
    переводятся в эталон, а вырезки по всему кадру стоили бы времени и ложных мячей с трибун.
    """

    def __init__(
        self,
        predict: Predict,
        frame_to_m: dict[int, np.ndarray],
        region_m: np.ndarray,
        frame_shape: tuple[int, int],
        tile: int,
        overlay: Iterable = (),
    ):
        from aifootball.geometry.registration import overlay_mask

        self.predict, self.frame_to_m, self.region_m = predict, frame_to_m, region_m
        self.shape, self.tile = frame_shape, tile
        self.overlay_keep = overlay_mask(frame_shape, overlay)

    @classmethod
    def for_venue(cls, weights: Path, venue, registration, frame_shape: tuple[int, int], conf: float, device: str):
        """Детектор по установке поворотной камеры (гомография эталона, графика) и привязке кадров к эталону."""
        from aifootball.geometry.registration import frame_homographies

        to_m = venue.require_homography()
        # Те же кадры, что потом переводятся в эталон (detections_to_reference): остальные рамки не нужны.
        frame_to_m = {frame_id: to_m @ H for frame_id, H in frame_homographies(registration).items()}
        return cls(
            yolo_predict(weights, venue.ball_tile, conf, device),
            frame_to_m,
            ptz_search_region_m(to_m, venue.length_m, venue.width_m),
            frame_shape,
            venue.ball_tile,
            venue.overlay,
        )

    def keep(self, frame_id: int) -> np.ndarray | None:
        A = self.frame_to_m.get(int(frame_id))
        return None if A is None else frame_keep_mask(A, self.region_m, self.shape, self.overlay_keep)

    def __call__(self, frame: np.ndarray, frame_id: int) -> tuple[np.ndarray, np.ndarray]:
        keep = self.keep(frame_id)
        if keep is None:
            return _no_boxes()
        x, y, bw, bh = cv2.boundingRect(keep)
        if bw == 0 or bh == 0:
            return _no_boxes()
        height, width = self.shape
        tiles = cover_tiles((x, y, x + bw, y + bh), self.tile, width, height)
        return detect_ball_in_frame(frame, keep, tiles, self.tile, self.predict)


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0
