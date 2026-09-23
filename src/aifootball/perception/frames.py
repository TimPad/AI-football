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


def iter_frames(video: Path, target_fps: float) -> Iterator[tuple[int, float, np.ndarray]]:
    """Отдаёт (номер кадра, время в секундах, кадр BGR) примерно с частотой target_fps.

    Отбор по времени, а не «каждый N-й кадр»: из 25 fps так получается ровно 10,
    а не 12.5, как дал бы шаг 2.
    """
    cap = _open(video)
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
