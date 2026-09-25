"""L1: сшивка оборванных треков на основе цвета и кинематической близости."""

import numpy as np
import polars as pl


def stitch_tracks(
    tracks: pl.DataFrame,
    max_gap_s: float = 5.0,
    max_color_dist: float = 15.0,
    max_spatial_dist_px: float = 150.0,
) -> pl.DataFrame:
    """Объединяет разделенные треки одного и того же игрока.

    Использует зазор во времени, совпадение цвета формы (Lab) и близкие
    координаты конца первого и начала второго трека.
    """
    if tracks.is_empty():
        return tracks

    # Собираем метаданные по каждому треку
    valid = tracks.filter(pl.col("in_pitch") & pl.col("torso_a").is_not_nan())
    if valid.is_empty():
        return tracks

    stats = (
        valid.group_by("track_id")
        .agg(
            start_ts=pl.col("ts").min(),
            end_ts=pl.col("ts").max(),
            a=pl.col("torso_a").median(),
            b=pl.col("torso_b").median(),
        )
        .sort("start_ts")
    )

    if len(stats) < 2:
        return tracks

    # Находим точки начала и конца каждого трека из исходного tracks
    start_pos = (
        tracks.sort("ts")
        .group_by("track_id", maintain_order=True)
        .agg(
            start_x=pl.col("foot_x").first(),
            start_y=pl.col("foot_y").first(),
        )
    )
    end_pos = (
        tracks.sort("ts")
        .group_by("track_id", maintain_order=True)
        .agg(
            end_x=pl.col("foot_x").last(),
            end_y=pl.col("foot_y").last(),
        )
    )

    meta = (
        stats.join(start_pos, on="track_id", how="inner")
        .join(end_pos, on="track_id", how="inner")
        .to_dicts()
    )

    # Составляем список кандидатов на сшивку (T_A -> T_B)
    candidates = []
    for i in range(len(meta)):
        ta = meta[i]
        for j in range(i + 1, len(meta)):
            tb = meta[j]
            dt = tb["start_ts"] - ta["end_ts"]
            if dt <= 0:
                continue
            if dt > max_gap_s:
                break  # meta отсортирован по start_ts

            color_dist = float(np.hypot(ta["a"] - tb["a"], ta["b"] - tb["b"]))
            if color_dist > max_color_dist:
                continue

            spatial_dist = float(np.hypot(tb["start_x"] - ta["end_x"], tb["start_y"] - ta["end_y"]))
            if spatial_dist > max_spatial_dist_px:
                continue

            cost = color_dist + 0.1 * spatial_dist + 2.0 * dt
            candidates.append((cost, ta["track_id"], tb["track_id"]))

    if not candidates:
        return tracks

    # Жадный выбор пар с наименьшей стоимостью (Union-Find)
    candidates.sort(key=lambda x: x[0])
    parent = {}

    def find(i: int) -> int:
        if parent.setdefault(i, i) == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    used_left = set()
    used_right = set()

    for cost, tid_a, tid_b in candidates:
        root_a = find(tid_a)
        root_b = find(tid_b)
        if root_a != root_b and tid_a not in used_left and tid_b not in used_right:
            parent[root_b] = root_a
            used_left.add(tid_a)
            used_right.add(tid_b)

    # Применяем маппинг старых track_id на новые
    mapping = {tid: find(tid) for tid in parent}
    if not mapping:
        return tracks

    mapping_df = pl.DataFrame(
        {"track_id": list(mapping.keys()), "new_track_id": list(mapping.values())},
        schema={"track_id": pl.Int32, "new_track_id": pl.Int32},
    )

    return (
        tracks.join(mapping_df, on="track_id", how="left")
        .with_columns(
            track_id=pl.when(pl.col("new_track_id").is_not_null())
            .then(pl.col("new_track_id"))
            .otherwise(pl.col("track_id"))
        )
        .drop("new_track_id")
        .sort("frame_id", "track_id")
    )
