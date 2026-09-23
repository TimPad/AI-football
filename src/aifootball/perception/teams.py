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


def assign_teams(tracks: pl.DataFrame) -> pl.DataFrame:
    """Заполняет role и team. Длинные треки на поле — player A/B, остальные — unknown."""
    per_track = (
        tracks.filter(pl.col("in_pitch") & pl.col("torso_a").is_not_nan())
        .group_by("track_id")
        .agg(
            n=pl.len(),
            a=pl.col("torso_a").median(),
            b=pl.col("torso_b").median(),
        )
        .filter(pl.col("n") >= MIN_OBSERVATIONS)
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


def _two_clusters(features: np.ndarray) -> list[str]:
    """k-means на 2 кластера. Имена стабильны: «A» — кластер с меньшим a (зеленее)."""
    cv2.setRNGSeed(0)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1)
    _, labels, centers = cv2.kmeans(features, 2, None, criteria, 5, cv2.KMEANS_PP_CENTERS)
    first = int(np.argmin(centers[:, 0]))
    return ["A" if label == first else "B" for label in labels.ravel()]
