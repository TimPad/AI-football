"""Таймы матча: автоматически по пустому полю или из флага --halves.

Перерыв — участок дольше BREAK_MIN_S, где на поле меньше ACTIVE_MIN_PEOPLE человек
(медиана по кадрам окна WINDOW_S). Короче — остановка внутри тайма (аут, замена, травма).
"""

from dataclasses import dataclass

import math
import re

import numpy as np
import polars as pl

BREAK_MIN_S = 120.0  # две минуты пустого поля отличают перерыв от короткой остановки
ACTIVE_MIN_PEOPLE = 4  # при меньшем числе людей окно считаем неигровым
WINDOW_S = 10.0  # медиана в окне подавляет короткие ошибки детекции


@dataclass(frozen=True)
class Period:
    key: str  # all | h1 | h2
    name: str
    spans: tuple[tuple[float, float], ...]

    @property
    def duration_s(self) -> float:
        return sum(end - start for start, end in self.spans)


def parse_halves(text: str, video_s: float) -> list[tuple[float, float]]:
    """«0:40-21:50,27:10-46:00» -> [(40, 1310), (1630, 2760)]; ошибка, если таймы пересекаются или вне записи."""
    spans = []
    for part in text.split(","):
        start, end = part.strip().split("-")
        spans.append((_seconds(start), _seconds(end)))
    if len(spans) not in (1, 2):
        raise ValueError("ожидается один или два тайма")
    spans.sort()
    for start, end in spans:
        if not 0 <= start < end <= video_s + 1e-6:
            raise ValueError(f"тайм {start:.0f}–{end:.0f} с вне записи 0–{video_s:.0f} с")
    for (_, end), (start, _) in zip(spans, spans[1:]):
        if start < end:
            raise ValueError("таймы пересекаются")
    return spans


def _seconds(clock: str) -> float:
    match = re.fullmatch(r"(\d+):(\d{1,2}(?:\.\d+)?)", clock.strip())
    if match is None:
        raise ValueError(f"неверное время: {clock!r}; ожидается м:сс")
    minutes, seconds = int(match[1]), float(match[2])
    if not math.isfinite(seconds) or seconds >= 60:
        raise ValueError(f"неверные секунды: {clock!r}")
    return minutes * 60 + seconds


def find_halves(tracks: pl.DataFrame) -> list[tuple[float, float]]:
    """Участки игры: один (перерыв не найден) или два — до и после самого длинного перерыва."""
    if tracks.is_empty():
        return []
    frames = tracks.select("frame_id", "ts").unique("frame_id")
    counts = tracks.filter(pl.col("in_pitch")).group_by("frame_id").agg(n=pl.len())
    per_frame = frames.join(counts, on="frame_id", how="left").with_columns(pl.col("n").fill_null(0))
    windows = (
        per_frame.with_columns(w=(pl.col("ts") // WINDOW_S).cast(pl.Int64))
        .group_by("w").agg(pl.col("n").median())
    )
    times = frames["ts"].sort().to_numpy()
    dt = np.diff(times)
    step = float(np.median(dt[dt > 0])) if np.any(dt > 0) else 0.0
    t_end = float(times[-1]) + step
    active = np.zeros(int(t_end // WINDOW_S) + 1, dtype=bool)
    active[windows["w"].to_numpy()] = windows["n"].to_numpy() >= ACTIVE_MIN_PEOPLE

    runs = _runs(active)
    if not runs:
        return []
    merged = [list(runs[0])]
    for start, end in runs[1:]:
        if (start - merged[-1][1]) * WINDOW_S < BREAK_MIN_S:
            merged[-1][1] = end  # короткая остановка внутри тайма
        else:
            merged.append([start, end])
    spans = [(start * WINDOW_S, min(end * WINDOW_S, t_end)) for start, end in merged]
    if len(spans) <= 2:
        return spans
    gaps = [b[0] - a[1] for a, b in zip(spans, spans[1:])]
    k = int(np.argmax(gaps))
    return [(spans[0][0], spans[k][1]), (spans[k + 1][0], spans[-1][1])]


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Отрезки [начало, конец) подряд идущих True."""
    padded = np.concatenate([[False], mask, [False]]).astype(int)
    edges = np.flatnonzero(np.diff(padded))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


def make_periods(spans: list[tuple[float, float]]) -> list[Period]:
    """«Весь матч» и, если таймов два, «1-й тайм» и «2-й тайм»."""
    periods = [Period("all", "Весь матч", tuple(spans))]
    if len(spans) == 2:
        periods += [Period("h1", "1-й тайм", (spans[0],)), Period("h2", "2-й тайм", (spans[1],))]
    return periods


def in_period(df: pl.DataFrame, spans) -> pl.DataFrame:
    """Строки с ts внутри любого из интервалов [начало, конец)."""
    cond = pl.lit(False)
    for start, end in spans:
        cond = cond | ((pl.col("ts") >= start) & (pl.col("ts") < end))
    return df.filter(cond)
