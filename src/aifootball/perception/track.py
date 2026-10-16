"""L1: трекинг людей по готовым детекциям -> tracks.parquet (без команд)."""

import numpy as np
import polars as pl
import supervision as sv
from trackers import ByteTrackTracker

from aifootball import schemas
from aifootball.geometry.polygons import points_in_polygon
from aifootball.venue import Venue

# Сколько держать потерянный трек. В trackers буфер задаётся в кадрах при 30 fps
# и сам пересчитывается под реальный fps: 90 = 3 секунды.
LOST_BUFFER_30FPS = 90
# Порог создания нового трека. Библиотечные 0.7 слишком строги: дальние игроки
# детектируются с уверенностью 0.3-0.6 и никогда бы не получили трек.
ACTIVATION_CONF = 0.4
HIGH_CONF = 0.5


def track_people(detections: pl.DataFrame, venue: Venue) -> pl.DataFrame:
    """Присваивает людям track_id, считает точку касания пола и флаг «на поле».

    Роль и команда здесь ещё не известны: role='unknown', team=null.
    Их заполняет perception.teams.assign_teams.
    """
    polygon = venue.require_polygon()
    people = detections.filter(pl.col("cls") == "person").sort("frame_id").with_row_index("row")
    if people.is_empty():
        return schemas.empty("tracks")

    tracker = ByteTrackTracker(
        lost_track_buffer=venue.lost_buffer_30fps,
        frame_rate=venue.target_fps,
        track_activation_threshold=ACTIVATION_CONF,
        high_conf_det_threshold=HIGH_CONF,
        minimum_consecutive_frames=2,
    )
    by_frame = {key[0]: group for key, group in people.partition_by("frame_id", as_dict=True).items()}
    # Кадры берём из всех детекций, включая мяч: трекер должен «увидеть» каждый
    # обработанный кадр, иначе неправильно отсчитает время жизни потерянных треков.
    # Кадр, где не нашлось вообще ничего, сюда не попадёт — на футзале с
    # 10 игроками в кадре такого не бывает.
    frames = detections.select("frame_id", "ts").unique("frame_id").sort("frame_id")

    rows: list[int] = []
    track_ids: list[int] = []
    for frame_id, ts in frames.iter_rows():
        group = by_frame.get(frame_id)
        if group is None:
            tracked = tracker.update(sv.Detections.empty(), timestamp=ts)
        else:
            tracked = tracker.update(
                sv.Detections(
                    xyxy=group.select("x1", "y1", "x2", "y2").to_numpy().astype(np.float32),
                    confidence=group["conf"].to_numpy().astype(np.float32),
                    class_id=np.zeros(len(group), dtype=int),
                    data={"row": group["row"].to_numpy()},
                ),
                timestamp=ts,
            )
        if len(tracked) == 0:
            continue
        confirmed = tracked.tracker_id >= 0  # -1 — трек ещё не подтверждён
        rows.extend(tracked.data["row"][confirmed].tolist())
        track_ids.extend(tracked.tracker_id[confirmed].tolist())

    assigned = pl.DataFrame(
        {"row": rows, "track_id": track_ids}, schema={"row": pl.UInt32, "track_id": pl.Int32}
    )
    tracked_people = people.join(assigned, on="row", how="inner").drop("row")

    foot_x, foot_y = _compute_robust_foot_points(tracked_people)
    foot = np.column_stack([foot_x, foot_y])

    return tracked_people.with_columns(
        foot_x=pl.Series(foot_x, dtype=pl.Float32),
        foot_y=pl.Series(foot_y, dtype=pl.Float32),
        in_pitch=pl.Series(points_in_polygon(foot, polygon)),
        role=pl.lit("unknown"),
        team=pl.lit(None, dtype=pl.Utf8),
    ).sort("frame_id", "track_id")


FOOT_WINDOW = 15  # кадров (~1 с при 15 fps) для медианы высоты бокса


def _compute_robust_foot_points(df: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Вычисляет робастную точку касания пола (foot_x, foot_y).

    Защищает от дёргания нижней грани бокса (y2), когда ноги уходят за край
    или перекрываются: если бокс заметно ниже обычного для этого трека, ноги
    восстанавливаются по верхней грани (y1) и обычной высоте. Обычная высота —
    медиана по соседним кадрам трека, а не по всему треку: вдали от камеры бокс
    вдвое ниже, и медиана за весь трек опускала ноги дальнего игрока на 40–80 px,
    то есть на несколько метров к камере (Ярославль, 12% строк).
    """
    x1 = df["x1"].to_numpy().astype(np.float64)
    y1 = df["y1"].to_numpy().astype(np.float64)
    x2 = df["x2"].to_numpy().astype(np.float64)
    y2 = df["y2"].to_numpy().astype(np.float64)
    track_ids = df["track_id"].to_numpy()
    frames = df["frame_id"].to_numpy() if "frame_id" in df.columns else np.arange(len(df))

    foot_x = (x1 + x2) / 2.0
    foot_y = y2.copy()

    half = FOOT_WINDOW // 2
    for tid in np.unique(track_ids):
        idx = np.flatnonzero(track_ids == tid)
        if len(idx) < 3:
            continue
        idx = idx[np.argsort(frames[idx], kind="stable")]
        h = y2[idx] - y1[idx]
        padded = np.pad(h, half, constant_values=np.nan)
        h_local = np.nanmedian(np.lib.stride_tricks.sliding_window_view(padded, FOOT_WINDOW), axis=1)
        # Бокс обрезан из-за смаза/перекрытия (h < 0.75 обычной) — ноги по верху головы и обычной высоте
        clipped = (h_local > 0) & (h < 0.75 * h_local)
        foot_y[idx[clipped]] = y1[idx[clipped]] + h_local[clipped]

    return foot_x.astype(np.float32), foot_y.astype(np.float32)
