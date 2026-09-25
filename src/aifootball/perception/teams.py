"""Базовое деление треков на две команды по цвету формы.

Это заведомо простая версия для фазы 1: вратари и судьи попадут в одну из
двух команд. Роли разделяются в фазе 3, после замера качества на валидации.
"""

import cv2
import numpy as np
import polars as pl

# Трек участвует в кластеризации, только если он достаточно долго был на поле:
# по короткому обрывку цвет формы определяется ненадёжно.
MIN_OBSERVATIONS = 10


def assign_teams(tracks: pl.DataFrame, min_observations: int = MIN_OBSERVATIONS) -> pl.DataFrame:
    """Заполняет role и team. Длинные треки на поле — player A/B, остальные — unknown."""
    per_track = (
        tracks.filter(pl.col("in_pitch") & pl.col("torso_a").is_not_nan())
        .group_by("track_id")
        .agg(
            n=pl.len(),
            a=pl.col("torso_a").median(),
            b=pl.col("torso_b").median(),
        )
        .filter(pl.col("n") >= min_observations)
        .sort("track_id")
    )
    if len(per_track) < 2:
        return tracks.with_columns(role=pl.lit("unknown"), team=pl.lit(None, dtype=pl.Utf8))

    # Только a и b (цветность), без яркости L: освещение в зале неровное,
    # а цвет формы от него почти не зависит.
    features = per_track.select("a", "b").to_numpy().astype(np.float32)
    labels = _two_clusters(features)
    teams = pl.DataFrame(
        {"track_id": per_track["track_id"], "team_new": labels},
        schema={"track_id": pl.Int32, "team_new": pl.Utf8},
    )
    return (
        tracks.drop("role", "team")
        .join(teams, on="track_id", how="left")
        .rename({"team_new": "team"})
        .with_columns(
            role=pl.when(pl.col("team").is_null()).then(pl.lit("unknown")).otherwise(pl.lit("player"))
        )
        .select(tracks.columns)
    )


def assign_roles(tracks: pl.DataFrame, venue) -> pl.DataFrame:
    """Выделяет роли 'goalkeeper' и 'referee' на основе позиции и поведения на поле.

    - Вратарь: игрок команды A/B, удерживающийся преимущественно в штрафной площади своих ворот.
    - Судья: объект, передвигающийся вдоль бровки/линий поля без захода в игровую зону.
    """
    if tracks.is_empty() or venue.H is None:
        return tracks

    from aifootball.geometry.homography import apply_homography
    from aifootball.geometry.undistort import undistort_points

    on_pitch = tracks.filter(pl.col("in_pitch"))
    if on_pitch.is_empty():
        return tracks

    pixels = on_pitch.select("foot_x", "foot_y").to_numpy()
    meters = apply_homography(venue.H, undistort_points(pixels, venue.calib))

    pos_df = on_pitch.select("track_id").with_columns(
        x_m=pl.Series(meters[:, 0]),
        y_m=pl.Series(meters[:, 1]),
    )

    track_stats = (
        pos_df.group_by("track_id")
        .agg(
            x_med=pl.col("x_m").median(),
            y_med=pl.col("y_m").median(),
            x_min=pl.col("x_m").min(),
            x_max=pl.col("x_m").max(),
            count=pl.len(),
        )
        .filter(pl.col("count") >= 5)
    )

    length_m = venue.length_m
    width_m = venue.width_m
    half_width = width_m / 2.0

    gk_tracks = {}
    ref_tracks = set()

    for row in track_stats.iter_rows(named=True):
        tid = row["track_id"]
        x_med = row["x_med"]
        y_med = row["y_med"]

        # Проверка на судью (движется вдоль самой бровки поля)
        if y_med < 0.4 or y_med > width_m - 0.4:
            ref_tracks.add(tid)
            continue

        # Проверка на вратаря: у ворот (в пределах 7м) и по центру ширины поля
        near_goal_a = (x_med < 7.0) and (abs(y_med - half_width) < 5.0) and (row["x_max"] < length_m / 2.0)
        near_goal_b = (x_med > length_m - 7.0) and (abs(y_med - half_width) < 5.0) and (row["x_min"] > length_m / 2.0)

        if near_goal_a:
            gk_tracks[tid] = "A"
        elif near_goal_b:
            gk_tracks[tid] = "B"

    if not gk_tracks and not ref_tracks:
        return tracks

    rows_role = []
    rows_team = []

    for row in tracks.iter_rows(named=True):
        tid = row["track_id"]
        current_role = row["role"]
        current_team = row["team"]

        if tid in ref_tracks:
            rows_role.append("referee")
            rows_team.append(None)
        elif tid in gk_tracks:
            rows_role.append("goalkeeper")
            rows_team.append(gk_tracks[tid])
        else:
            rows_role.append(current_role)
            rows_team.append(current_team)

    return tracks.with_columns(
        role=pl.Series(rows_role, dtype=pl.Utf8),
        team=pl.Series(rows_team, dtype=pl.Utf8),
    )


def _two_clusters(features: np.ndarray) -> list[str]:
    """k-means на 2 кластера. Имена стабильны: «A» — кластер с меньшим a (зеленее)."""
    cv2.setRNGSeed(0)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1)
    _, labels, centers = cv2.kmeans(features, 2, None, criteria, 5, cv2.KMEANS_PP_CENTERS)
    first = int(np.argmin(centers[:, 0]))
    return ["A" if label == first else "B" for label in labels.ravel()]
