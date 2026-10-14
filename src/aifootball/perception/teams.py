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
# Короткая атака у ворот не должна превращать полевого игрока во вратаря.
GOALKEEPER_MIN_S = 20.0
GOAL_ZONE_M = 7.0  # зона у ворот с запасом относительно штрафной
GOAL_CENTER_M = 5.0  # ширина зоны относительно центра ворот


def assign_teams(tracks: pl.DataFrame, min_observations: int = MIN_OBSERVATIONS) -> pl.DataFrame:
    """Заполняет role и team. Длинные треки на поле — player A/B, остальные — unknown."""
    per_track = _track_colors(tracks, min_observations)
    if len(per_track) < 2:
        return tracks.with_columns(role=pl.lit("unknown"), team=pl.lit(None, dtype=pl.Utf8))

    labels, _ = _two_clusters(per_track.select("a", "b").to_numpy().astype(np.float32))
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


def team_color_centers(tracks: pl.DataFrame, min_observations: int = MIN_OBSERVATIONS) -> np.ndarray | None:
    """Цвет формы команд (a, b): строка 0 — A, строка 1 — B, как в assign_teams. None — треков меньше двух."""
    per_track = _track_colors(tracks, min_observations)
    if len(per_track) < 2:
        return None
    _, centers = _two_clusters(per_track.select("a", "b").to_numpy().astype(np.float32))
    return centers


def _track_colors(tracks: pl.DataFrame, min_observations: int) -> pl.DataFrame:
    """Медианный цвет торса (a, b) каждого трека, достаточно долго бывшего на поле.

    Только a и b (цветность), без яркости L: освещение в зале неровное,
    а цвет формы от него почти не зависит.
    """
    return (
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

    pos_df = on_pitch.select("frame_id", "ts", "track_id", "team", "role", "in_pitch").with_columns(
        x_m=pl.Series(meters[:, 0]),
        y_m=pl.Series(meters[:, 1]),
    )

    from aifootball.analytics.periods import find_halves, in_period
    from aifootball.state.smooth import MAX_GAP_S

    spans = find_halves(tracks)
    if not spans:
        spans = [(float(tracks["ts"].min()), float(tracks["ts"].max()) + 1e-6)]
    # Роль одна на трек; направление и команда вратаря определяются по каждому тайму.
    gk_tracks = {}
    ref_tracks = set()
    for span in spans:
        part = in_period(pos_df, [span])
        candidates = {}
        for (tid,), g in part.sort("track_id", "ts").group_by("track_id", maintain_order=True):
            x, y, ts = (g[c].to_numpy() for c in ("x_m", "y_m", "ts"))
            if len(ts) < 5:
                continue
            y_med = float(np.median(y))
            if y_med < 0.4 or y_med > venue.width_m - 0.4:
                ref_tracks.add(tid)
                continue
            dt = np.diff(ts)
            continuous = (dt > 0) & (dt <= MAX_GAP_S)
            for side, near in (
                ("left", (x < GOAL_ZONE_M) & (abs(y - venue.width_m / 2) < GOAL_CENTER_M)),
                ("right", (x > venue.length_m - GOAL_ZONE_M) & (abs(y - venue.width_m / 2) < GOAL_CENTER_M)),
            ):
                observed = float(dt[continuous & near[:-1] & near[1:]].sum())
                stays_on_side = np.all(x < venue.length_m / 2) if side == "left" else np.all(x > venue.length_m / 2)
                if observed >= GOALKEEPER_MIN_S and stays_on_side:
                    candidates[tid] = side
        field = part.filter(~pl.col("track_id").is_in([*candidates, *ref_tracks]))
        sides = defending_sides(field)
        for tid, side in candidates.items():
            original = part.filter(pl.col("track_id") == tid)["team"].mode().first()
            gk_tracks[tid] = (sides[0 if side == "left" else 1] if sides else original)

    if not gk_tracks and not ref_tracks:
        return tracks
    return tracks.with_columns(
        role=pl.Series([
            "referee" if tid in ref_tracks else "goalkeeper" if tid in gk_tracks else role
            for tid, role in tracks.select("track_id", "role").iter_rows()
        ], dtype=pl.Utf8),
        team=pl.Series([
            None if tid in ref_tracks else gk_tracks.get(tid, team)
            for tid, team in tracks.select("track_id", "team").iter_rows()
        ], dtype=pl.Utf8),
    )


def defending_sides(positions: pl.DataFrame) -> tuple[str, str] | None:
    """Команды у левых и правых ворот по медиане полевых игроков; None — данных недостаточно."""
    med = (positions.filter(pl.col("team").is_in(["A", "B"]) & (pl.col("role") == "player"))
           .group_by("team").agg(pl.col("x_m").median()).sort("x_m"))
    if med.height != 2 or abs(med["x_m"][0] - med["x_m"][1]) < 1e-6:
        return None
    left = med["team"][0]
    return left, "B" if left == "A" else "A"


def _two_clusters(features: np.ndarray) -> tuple[list[str], np.ndarray]:
    """k-means на 2 кластера: метки и центры (A, B). Имена стабильны: «A» — кластер с меньшим a (зеленее)."""
    cv2.setRNGSeed(0)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1)
    _, labels, centers = cv2.kmeans(features, 2, None, criteria, 5, cv2.KMEANS_PP_CENTERS)
    first = int(np.argmin(centers[:, 0]))
    names = ["A" if label == first else "B" for label in labels.ravel()]
    return names, centers[[first, 1 - first]].astype(float)
