"""Чтение кадров видео с прореживанием до целевого fps."""

import math
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

# Метки соседних кадров различаются на миллисекунды и больше; совпадение метки определяет кадр.
SAME_FRAME_S = 1e-4


def video_fps(video: Path) -> float:
    cap = _open(video)
    try:
        return cap.get(cv2.CAP_PROP_FPS)
    finally:
        cap.release()


def frame_time(cap: cv2.VideoCapture) -> float:
    """Метка последнего прочитанного кадра (pts от начала потока), с, с точностью до микросекунды."""
    return round(cap.get(cv2.CAP_PROP_POS_MSEC) * 1000) / 1_000_000


def last_frame_time(video: Path, estimate_s: float) -> float | None:
    """Метка последнего декодируемого кадра: перемотка к концу и чтение до конца файла.

    estimate_s — длительность по числу кадров контейнера. Она бывает длиннее записи (кадры с отрицательной
    меткой декодер отбрасывает), и перемотка за конец не читает ничего: тогда отступаем дальше.
    """
    for back_s in (5.0, 60.0, None):
        if back_s is not None and estimate_s - back_s <= 0:
            continue
        cap = _open(video)
        try:
            if back_s is not None:
                cap.set(cv2.CAP_PROP_POS_MSEC, (estimate_s - back_s) * 1000)
            last = None
            while cap.grab():
                last = frame_time(cap)
            if last is not None:
                return last
        finally:
            cap.release()
    return None


def iter_frames(
    video: Path,
    target_fps: float,
    *,
    expected_width: int | None = None,
    expected_height: int | None = None,
    start_ms: int = 0,
    end_ms: int | None = None,
    seek: bool = True,
    after: tuple[int, float] | None = None,
) -> Iterator[tuple[int, float, np.ndarray]]:
    """Отдаёт (номер кадра, время в секундах, кадр BGR) примерно с частотой target_fps.

    Номер — порядковый номер декодированного кадра от начала файла, время — метка кадра в потоке. На загрузках
    трансляций шаг кадров плавает (33–37 мс), и номер / fps расходится с меткой до 2 с, поэтому время берётся
    из метки. Окно [start_ms, end_ms) — тоже по метке.

    Отбор по номеру на сетке target_fps, а не «каждый N-й кадр»: из 25 fps так получается ровно 10, а не 12.5,
    как дал бы шаг 2; при target_fps не ниже частоты видео берётся каждый кадр. Отбор не зависит от окна:
    кадры окна те же, что у прохода от начала.

    Переход к start_ms:
    - after=(номер, время) кадра, уже прочитанного проходом от начала: перемотка к нему по времени и сверка
      метки. Номера и время дальше те же, что при чтении подряд; не нашёлся кадр — чтение подряд.
    - без after OpenCV перематывает по времени, а номер считает по fps: верно только при постоянном шаге кадров
      (на записи ВШЭ перемотка на кадр 50000 даёт кадр, который подряд идёт 50050-м).
    - seek=False — только чтение подряд.
    """
    if (
        not math.isfinite(target_fps)
        or target_fps <= 0
        or type(start_ms) is not int
        or start_ms < 0
        or (end_ms is not None and (type(end_ms) is not int or end_ms <= start_ms))
        or (
            after is not None
            and (type(after[0]) is not int or after[0] < 0 or not math.isfinite(after[1]) or after[1] < 0)
        )
    ):
        raise ValueError('Неверные параметры выборки кадров')
    cap = _open(video)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if (expected_width is not None and width != expected_width) or (
        expected_height is not None and height != expected_height
    ):
        cap.release()
        raise ValueError(
            f'{video}: разрешение видео {width} × {height} не соответствует профилю камеры '
            f'{expected_width} × {expected_height}. Выберите подходящий профиль.'
        )
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if not math.isfinite(src_fps) or src_fps <= 0:
        cap.release()
        raise ValueError(f'{video}: видео не сообщает fps')
    sample_fps = min(target_fps, src_fps)
    frame_id, previous = 0, -math.inf  # номер следующего кадра, метка предыдущего
    if seek and after is not None and after[1] * 1000 < start_ms:
        frame_id = _seek_after(cap, *after)
        previous = after[1]
    elif seek and after is None and start_ms:
        frame_id = _seek_by_fps(cap, start_ms, src_fps)
    if frame_id is None:
        cap.release()
        cap = _open(video)
        frame_id, previous = 0, -math.inf
    taken = 0
    for earlier in range(frame_id):
        if _sampled(earlier, taken, src_fps, sample_fps):
            taken += 1
    try:
        while cap.grab():
            ts = frame_time(cap)
            if not ts > previous:
                raise ValueError(f'{video}: метки времени кадров не возрастают (кадр {frame_id}, {ts:.3f} с)')
            previous = ts
            if end_ms is not None and ts >= end_ms / 1000:
                break
            if _sampled(frame_id, taken, src_fps, sample_fps):
                taken += 1
                if ts >= start_ms / 1000:
                    ok, frame = cap.retrieve()
                    if not ok:
                        break
                    if (expected_width is not None and frame.shape[1] != expected_width) or (
                        expected_height is not None and frame.shape[0] != expected_height
                    ):
                        raise ValueError(f'{video}: разрешение декодированного кадра не соответствует профилю камеры')
                    yield frame_id, ts, frame
            frame_id += 1
    finally:
        cap.release()


def _sampled(frame_id: int, taken: int, src_fps: float, sample_fps: float) -> bool:
    return frame_id / src_fps + 1e-6 >= taken / sample_fps


def _seek_after(cap: cv2.VideoCapture, frame_id: int, ts: float) -> int | None:
    """Ставит чтение сразу за кадром (frame_id, ts) прохода от начала; номер следующего кадра или None.

    Перемотка останавливается на кадре чуть раньше цели (его метка видна до следующего grab), дальше читаем
    до кадра с той же меткой. Метка у кадра одна, поэтому совпадение определяет и номер. OpenCV после опорного
    кадра считает кадры подряд, а время — по fps, и при плавающем шаге может остановиться позже цели: тогда
    отступаем дальше.
    """
    for back_s in (1.0, 10.0, 60.0):
        if ts - back_s <= 0:
            return None  # кадр в начале записи: прочитать подряд дешевле
        cap.set(cv2.CAP_PROP_POS_MSEC, (ts - back_s) * 1000)
        current = frame_time(cap)
        if current > ts + SAME_FRAME_S:
            continue  # перемотка проскочила кадр: отступаем дальше
        while current < ts - SAME_FRAME_S:
            if not cap.grab():
                return None
            current = frame_time(cap)
        return frame_id + 1 if abs(current - ts) <= SAME_FRAME_S else None
    return None


def _seek_by_fps(cap: cv2.VideoCapture, start_ms: int, src_fps: float) -> int | None:
    frame_id = int(math.floor(start_ms / 1000 * src_fps))
    if frame_id:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        if abs(cap.get(cv2.CAP_PROP_POS_FRAMES) - frame_id) > 0.5:
            return None
    return frame_id


def _open(video: Path) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FileNotFoundError(f'не открывается видео: {video}')
    return cap
