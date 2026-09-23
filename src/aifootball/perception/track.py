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
        lost_track_buffer=LOST_BUFFER_30FPS,
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

    foot = np.column_stack([
        ((tracked_people["x1"] + tracked_people["x2"]) / 2).to_numpy(),
        tracked_people["y2"].to_numpy(),
    ])
    return tracked_people.with_columns(
        foot_x=pl.Series(foot[:, 0], dtype=pl.Float32),
        foot_y=pl.Series(foot[:, 1], dtype=pl.Float32),
        in_pitch=pl.Series(points_in_polygon(foot, polygon)),
        role=pl.lit("unknown"),
        team=pl.lit(None, dtype=pl.Utf8),
    ).sort("frame_id", "track_id")
