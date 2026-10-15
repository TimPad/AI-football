"""Чтение кадров видео с прореживанием до целевого fps."""

from collections.abc import Iterator
from pathlib import Path
import math

import cv2
import numpy as np


def video_fps(video: Path) -> float:
    cap = _open(video)
    try:
        return cap.get(cv2.CAP_PROP_FPS)
    finally:
        cap.release()


def iter_frames(video: Path, target_fps: float, *, expected_width: int | None = None,
                expected_height: int | None = None, start_ms: int = 0,
                end_ms: int | None = None) -> Iterator[tuple[int, float, np.ndarray]]:
    """Отдаёт (номер кадра, время в секундах, кадр BGR) примерно с частотой target_fps.

    Отбор по времени, а не «каждый N-й кадр»: из 25 fps так получается ровно 10,
    а не 12.5, как дал бы шаг 2.
    """
    if not math.isfinite(target_fps) or target_fps <= 0 or type(start_ms) is not int or start_ms < 0 or (end_ms is not None and (type(end_ms) is not int or end_ms <= start_ms)):
        raise ValueError('Неверные параметры выборки кадров')
    cap = _open(video)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if (expected_width is not None and width != expected_width) or (expected_height is not None and height != expected_height):
        cap.release()
        raise ValueError(f"{video}: разрешение видео {width} × {height} не соответствует профилю камеры "
                         f"{expected_width} × {expected_height}. Выберите подходящий профиль.")
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if not math.isfinite(src_fps) or src_fps <= 0:
        cap.release()
        raise ValueError(f"{video}: видео не сообщает fps")
    sample_fps = min(target_fps, src_fps)
    taken = max(0, math.ceil(start_ms / 1000 * sample_fps - 1e-6))
    frame_id = int(math.floor(start_ms / 1000 * src_fps))
    if frame_id:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        if abs(cap.get(cv2.CAP_PROP_POS_FRAMES) - frame_id) > .5:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            for _ in range(frame_id):
                if not cap.grab():
                    cap.release()
                    raise ValueError('Не удалось перейти к кадру исходника')
    try:
        while cap.grab():
            ts = frame_id / src_fps
            if end_ms is not None and ts >= end_ms / 1000:
                break
            if ts + 1e-6 >= taken / sample_fps:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                if (expected_width is not None and frame.shape[1] != expected_width) or (expected_height is not None and frame.shape[0] != expected_height):
                    raise ValueError(f"{video}: разрешение декодированного кадра не соответствует профилю камеры")
                yield frame_id, ts, frame
                taken += 1
            frame_id += 1
    finally:
        cap.release()


def _open(video: Path) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FileNotFoundError(f"не открывается видео: {video}")
    return cap
