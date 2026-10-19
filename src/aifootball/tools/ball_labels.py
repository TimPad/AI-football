"""Эталонная разметка мяча: выбор кадров, хранение меток, отрисовка окна разметки."""

from pathlib import Path

import cv2
import numpy as np
import polars as pl

from aifootball import schemas

STATUSES = ("visible", "absent", "hidden")
LOUPE_HALF_PX = 24  # лупа показывает 48x48 пикселей кадра вокруг курсора
LOUPE_ZOOM = 5


def sampled_frame_ids(total_frames: int, src_fps: float, target_fps: float) -> list[int]:
    """Номера кадров, которые отдаёт iter_frames: то же правило отбора по времени."""
    ids = []
    for frame_id in range(total_frames):
        if frame_id / src_fps + 1e-6 >= len(ids) / target_fps:
            ids.append(frame_id)
    return ids


def spread(ids: list[int], count: int) -> list[int]:
    """count кадров, равномерно разнесённых по всему видео."""
    if count >= len(ids):
        return list(ids)
    picks = np.linspace(0, len(ids) - 1, count).round().astype(int)
    return [ids[i] for i in picks]


class BallLabels:
    """Метки по кадрам. Каждое изменение сразу пишется на диск: разметку можно прервать."""

    def __init__(self, path: Path, src_fps: float):
        self.path = path
        self.src_fps = src_fps
        self._labels: dict[int, dict] = {}
        if path.exists():
            for row in schemas.read(path, "ball_labels").iter_rows(named=True):
                self._labels[row["frame_id"]] = {"status": row["status"], "x": row["x"], "y": row["y"]}

    def get(self, frame_id: int) -> dict | None:
        return self._labels.get(frame_id)

    def set(self, frame_id: int, status: str, point: tuple[float, float] | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"неизвестный статус {status!r}, допустимы {STATUSES}")
        if (status == "visible") != (point is not None):
            raise ValueError("точка мяча нужна у visible и только у него")
        x, y = point if point is not None else (None, None)
        self._labels[frame_id] = {"status": status, "x": x, "y": y}
        self._save()

    def first_unlabeled(self, frame_ids: list[int]) -> int:
        for i, frame_id in enumerate(frame_ids):
            if frame_id not in self._labels:
                return i
        return len(frame_ids)

    def counts(self) -> dict[str, int]:
        found = {status: 0 for status in STATUSES}
        for label in self._labels.values():
            found[label["status"]] += 1
        return found

    def _save(self) -> None:
        ids = sorted(self._labels)
        df = pl.DataFrame({
            "frame_id": ids,
            "ts": [round(i / self.src_fps, 4) for i in ids],
            "status": [self._labels[i]["status"] for i in ids],
            "x": [self._labels[i]["x"] for i in ids],
            "y": [self._labels[i]["y"] for i in ids],
        }, schema=schemas.BALL_LABELS)
        schemas.write(df, self.path, "ball_labels")


def render_view(
    frame: np.ndarray,
    scale: float,
    label: dict | None,
    cursor: tuple[int, int] | None,
    header: str,
    border_bgr: tuple[int, int, int] | None = None,
) -> np.ndarray:
    """Кадр для окна разметки: метка, строка состояния и лупа вокруг курсора.

    cursor — в пикселях исходного кадра. Текст только ASCII: кириллицу OpenCV не рисует.
    """
    shown = cv2.resize(frame, None, fx=scale, fy=scale) if scale != 1 else frame.copy()
    if label is not None and label["status"] == "visible":
        center = (int(label["x"] * scale), int(label["y"] * scale))
        cv2.circle(shown, center, int(12 * scale), (0, 0, 255), 2)
    status = f"  [{label['status']}]" if label is not None else ""
    _text(shown, header + status, (10, 30))
    if cursor is not None:
        _draw_loupe(shown, frame, cursor)
    if border_bgr is not None:
        cv2.rectangle(shown, (0, 0), (shown.shape[1] - 1, shown.shape[0] - 1), border_bgr, 6)
    return shown


def _draw_loupe(shown: np.ndarray, frame: np.ndarray, cursor: tuple[int, int]) -> None:
    """Увеличенный участок кадра в правом верхнем углу: там стены зала, поле не закрывает."""
    r = LOUPE_HALF_PX
    padded = cv2.copyMakeBorder(frame, r, r, r, r, cv2.BORDER_CONSTANT)
    # Окно OpenCV сообщает курсор и за своим краем — лупа показывает ближайший край кадра.
    x = min(max(cursor[0], 0), frame.shape[1] - 1)
    y = min(max(cursor[1], 0), frame.shape[0] - 1)
    crop = padded[y:y + 2 * r, x:x + 2 * r]
    zoomed = cv2.resize(crop, None, fx=LOUPE_ZOOM, fy=LOUPE_ZOOM, interpolation=cv2.INTER_CUBIC)
    size = zoomed.shape[0]
    mid = size // 2
    cv2.line(zoomed, (mid - 12, mid), (mid - 4, mid), (0, 0, 255), 1)
    cv2.line(zoomed, (mid + 4, mid), (mid + 12, mid), (0, 0, 255), 1)
    cv2.line(zoomed, (mid, mid - 12), (mid, mid - 4), (0, 0, 255), 1)
    cv2.line(zoomed, (mid, mid + 4), (mid, mid + 12), (0, 0, 255), 1)
    x0 = shown.shape[1] - size - 10
    if x0 < 0 or size + 10 > shown.shape[0]:
        return
    shown[10:10 + size, x0:x0 + size] = zoomed
    cv2.rectangle(shown, (x0 - 1, 9), (x0 + size, 10 + size), (255, 255, 255), 1)


def _text(img: np.ndarray, text: str, org: tuple[int, int]) -> None:
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
