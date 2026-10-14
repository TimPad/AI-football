"""Чтение кадров видео с прореживанием до целевого fps."""

from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np


def video_fps(video: Path) -> float:
    cap = _open(video)
    try:
        return cap.get(cv2.CAP_PROP_FPS)
    finally:
        cap.release()


def iter_frames(video: Path, target_fps: float, *, expected_width: int | None = None,
                expected_height: int | None = None) -> Iterator[tuple[int, float, np.ndarray]]:
    """Отдаёт (номер кадра, время в секундах, кадр BGR) примерно с частотой target_fps.

    Отбор по времени, а не «каждый N-й кадр»: из 25 fps так получается ровно 10,
    а не 12.5, как дал бы шаг 2.
    """
    cap = _open(video)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if (expected_width is not None and width != expected_width) or (expected_height is not None and height != expected_height):
        cap.release()
        raise ValueError(f"{video}: разрешение видео {width} × {height} не соответствует профилю камеры "
                         f"{expected_width} × {expected_height}. Выберите подходящий профиль.")
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if src_fps <= 0:
        cap.release()
        raise ValueError(f"{video}: видео не сообщает fps")
    taken = 0
    frame_id = 0
    try:
        while cap.grab():
            ts = frame_id / src_fps
            if ts + 1e-6 >= taken / target_fps:
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
