"""Картинки для отчёта: миниатюры игроков и стоп-кадры моментов, JPEG в base64 (data URI)."""

import base64
from pathlib import Path

import cv2
import numpy as np

THUMB_H = 120
STILL_W = 640
JPEG_QUALITY = 80
THUMB_PAD = 0.15  # запас вокруг рамки игрока
STILL_CONTEXT = 6.0  # стоп-кадр с игроком: окно шириной в столько ростов игрока
STILL_MIN_W = 480  # px исходного кадра
BOX_BGR = (0, 230, 255)


def grab_images(video: Path, requests: dict[str, dict]) -> dict[str, str]:
    """requests: ключ -> {kind: thumb|still, frame_id, box: [x1, y1, x2, y2] | None}. Нечитаемые кадры пропускаются."""
    cap = cv2.VideoCapture(str(video))
    out = {}
    try:
        for key, req in sorted(requests.items(), key=lambda kv: kv[1]["frame_id"]):
            cap.set(cv2.CAP_PROP_POS_FRAMES, req["frame_id"])
            ok, frame = cap.read()
            if not ok:
                continue
            image = _thumb(frame, req["box"]) if req["kind"] == "thumb" else _still(frame, req["box"])
            ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok:
                out[key] = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")
    finally:
        cap.release()
    return out


def _clip(frame: np.ndarray, x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    h, w = frame.shape[:2]
    x1, x2 = int(max(0, x1)), int(min(w, x2))
    y1, y2 = int(max(0, y1)), int(min(h, y2))
    return frame[y1:max(y2, y1 + 1), x1:max(x2, x1 + 1)]


def _thumb(frame: np.ndarray, box) -> np.ndarray:
    x1, y1, x2, y2 = box
    pw, ph = (x2 - x1) * THUMB_PAD, (y2 - y1) * THUMB_PAD
    crop = _clip(frame, x1 - pw, y1 - ph, x2 + pw, y2 + ph)
    scale = THUMB_H / crop.shape[0]
    return cv2.resize(crop, (max(1, int(round(crop.shape[1] * scale))), THUMB_H))


def _still(frame: np.ndarray, box) -> np.ndarray:
    image = frame.copy()
    if box is not None:
        x1, y1, x2, y2 = box
        cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), BOX_BGR, 3)
        win_w = max(STILL_MIN_W, STILL_CONTEXT * (y2 - y1))
        win_h = win_w * 3 / 4
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        image = _clip(image, cx - win_w / 2, cy - win_h / 2, cx + win_w / 2, cy + win_h / 2)
    scale = STILL_W / image.shape[1]
    return cv2.resize(image, (STILL_W, max(1, int(round(image.shape[0] * scale)))))
