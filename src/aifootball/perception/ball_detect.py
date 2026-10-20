"""L1: детекция мяча дообученной моделью — по закрашенному кадру, вырезками в полном разрешении.

Мяч в кадре 5 Мп занимает 12–20 px; ужми кадр до 1280 — станет 6–10 px, и модель его не видит.
Поэтому кадр режется на перекрывающиеся вырезки tile x tile без масштабирования. Всё дальше
запаса за контуром поля закрашивается серым так же, как при обучении (tools.ball_dataset):
иначе модель находит запасные мячи у скамейки.
"""

from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

FILL_BGR = (114, 114, 114)  # серый, которым YOLO сам заполняет поля при letterbox
MERGE_IOU = 0.3  # один мяч на стыке двух вырезок

# predict(вырезки) -> для каждой вырезки (боксы xyxy в её координатах, уверенности)
Predict = Callable[[list[np.ndarray]], list[tuple[np.ndarray, np.ndarray]]]


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
    crops = [masked[y0:y0 + tile, x0:x0 + tile] for x0, y0 in tiles]
    all_boxes, all_confs = [], []
    for (x0, y0), (boxes, confs) in zip(tiles, predict(crops)):
        if len(boxes):
            all_boxes.append(np.asarray(boxes, float) + [x0, y0, x0, y0])
            all_confs.append(np.asarray(confs, float))
    if not all_boxes:
        return np.zeros((0, 4)), np.zeros(0)
    return merge_tile_boxes(np.vstack(all_boxes), np.concatenate(all_confs))


class BallDetector:
    """Дообученная модель мяча, настроенная на кадр определённого размера и установку."""

    def __init__(self, weights: Path, polygon: np.ndarray, frame_shape: tuple[int, int], tile: int,
                 margin_px: int, conf: float, device: str):
        from ultralytics import YOLO  # тяжёлый импорт — только когда реально детектируем

        if not weights.exists():
            raise FileNotFoundError(f"нет весов модели мяча: {weights}")
        self.model = YOLO(str(weights))
        self.tile, self.conf, self.device = tile, conf, device
        height, width = frame_shape
        self.keep = pitch_keep_mask(frame_shape, polygon, margin_px)
        ys, xs = np.nonzero(self.keep)
        self.tiles = cover_tiles((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1),
                                 tile, width, height)

    def __call__(self, frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return detect_ball_in_frame(frame, self.keep, self.tiles, self.tile, self._predict)

    def _predict(self, crops: list[np.ndarray]) -> list[tuple[np.ndarray, np.ndarray]]:
        results = self.model.predict(crops, imgsz=self.tile, device=self.device, conf=self.conf, verbose=False)
        return [(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()) for r in results]


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0
