"""L3: state.parquet -> metrics.json.

Каждая метрика идёт вместе с observed_s — сколько секунд объект реально был
виден на поле. Без этого дистанция игрока, ушедшего из кадра, молча занижается.
"""

import math

import numpy as np
import polars as pl

from aifootball import schemas
from aifootball.state.smooth import MAX_GAP_S

import cv2

HEATMAP_CELL_M = 1.0
TEAMS = ("A", "B")
SPRINT_THRESHOLD_MS = 5.0
SPRINT_MIN_DURATION_S = 1.0


def compute_metrics(
    state: pl.DataFrame,
    length_m: float,
    width_m: float,
    ball_state: pl.DataFrame | None = None,
) -> dict:
    tracks = {
        str(track_id): _track_metrics(group)
        for (track_id,), group in state.sort("track_id", "ts").group_by("track_id", maintain_order=True)
    }
    sample_s = _sampling_step(state)
    teams = {}
    for team in TEAMS:
        members = sorted((tid for tid, m in tracks.items() if m["team"] == team), key=int)
        team_state = state.filter(pl.col("team") == team)
        teams[team] = {
            "tracks": members,
            "observed_s": round(sum(tracks[t]["observed_s"] for t in members), 2),
            "distance_m": round(sum(tracks[t]["distance_m"] for t in members), 2),
            "sprints_count": sum(tracks[t]["sprints_count"] for t in members),
            "compactness_m2": _team_compactness(team_state),
            # heatmap_s[ix][iy] — секунды, проведённые игроками команды в клетке 1x1 м
            "heatmap_s": _heatmap(team_state, length_m, width_m, sample_s),
        }
    
    result = {
        "schema_version": schemas.SCHEMA_VERSION,
        "pitch": {"length_m": length_m, "width_m": width_m, "heatmap_cell_m": HEATMAP_CELL_M},
        "teams": teams,
        "tracks": tracks,
    }

    if ball_state is not None and not ball_state.is_empty():
        from aifootball.perception.ball import compute_possession, detect_passes
        result["possession"] = compute_possession(ball_state, state)
        result["passes"] = detect_passes(ball_state, state)

    return result


def _track_metrics(g: pl.DataFrame) -> dict:
    ts = g["ts"].to_numpy()
    x, y = g["x_m"].to_numpy(), g["y_m"].to_numpy()
    speed = g["speed"].to_numpy()
    dt = np.diff(ts)
    steps = np.hypot(np.diff(x), np.diff(y))
    continuous = dt <= MAX_GAP_S  # через длинный разрыв расстояние не считаем
    observed = float(dt[continuous].sum())
    distance = float(steps[continuous].sum())
    sprints = _count_sprints(speed, ts)
    return {
        "team": g["team"][0],
        "role": g["role"][0],
        "observed_s": round(observed, 2),
        "distance_m": round(distance, 2),
        "distance_per_min": round(distance / observed * 60, 1) if observed > 0 else 0.0,
        "max_speed_ms": round(float(g["speed"].max()), 2),
        "sprints_count": sprints,
    }


def _count_sprints(speed: np.ndarray, ts: np.ndarray) -> int:
    if len(speed) < 2:
        return 0
    sprints = 0
    in_sprint = False
    sprint_start_ts = 0.0
    for s, t in zip(speed, ts):
        if s >= SPRINT_THRESHOLD_MS:
            if not in_sprint:
                in_sprint = True
                sprint_start_ts = t
        else:
            if in_sprint:
                if (t - sprint_start_ts) >= SPRINT_MIN_DURATION_S:
                    sprints += 1
                in_sprint = False
    if in_sprint and (ts[-1] - sprint_start_ts) >= SPRINT_MIN_DURATION_S:
        sprints += 1
    return sprints


def _team_compactness(team_state: pl.DataFrame) -> float:
    if team_state.is_empty():
        return 0.0

    areas = []
    for _, group in team_state.group_by("frame_id"):
        if len(group) >= 3:
            pts = group.select("x_m", "y_m").to_numpy().astype(np.float32)
            hull = cv2.convexHull(pts)
            area = float(cv2.contourArea(hull))
            areas.append(area)

    return round(float(np.mean(areas)), 2) if areas else 0.0


def _sampling_step(state: pl.DataFrame) -> float:
    """Шаг между отсчётами внутри трека (при 10 fps — 0.1 с)."""
    diffs = (
        state.sort("track_id", "ts")
        .select(pl.col("ts").diff().over("track_id").alias("dt"))
        .filter(pl.col("dt") > 0)["dt"]
    )
    return float(diffs.median()) if len(diffs) else 0.0


def _heatmap(team_state: pl.DataFrame, length_m: float, width_m: float, sample_s: float) -> list:
    nx = math.ceil(length_m / HEATMAP_CELL_M)
    ny = math.ceil(width_m / HEATMAP_CELL_M)
    if team_state.is_empty():
        return np.zeros((nx, ny)).tolist()
    # Ограничиваем координаты границами поля [0, length_m) и [0, width_m),
    # чтобы точки на линиях или с допустимым вылетом за пределы поля не отбрасывались
    x = np.clip(team_state["x_m"].to_numpy(), 0.0, length_m - 1e-5)
    y = np.clip(team_state["y_m"].to_numpy(), 0.0, width_m - 1e-5)
    hist, _, _ = np.histogram2d(
        x,
        y,
        bins=[nx, ny],
        range=[[0, length_m], [0, width_m]],
    )
    return (hist * sample_s).round(2).tolist()
