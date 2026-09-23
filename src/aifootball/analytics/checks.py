"""Критерии готовности фазы 1 — считаются по state.parquet."""

import polars as pl

MAX_SPEED_MS = 10.0  # быстрее футзалист не бегает; больше — значит, врёт трекинг или гомография
MIN_INSIDE_SHARE = 0.95
EDGE_TOLERANCE_M = 0.5  # игрок на линии поля — не вылет


def phase1_checks(state: pl.DataFrame, length_m: float, width_m: float) -> dict:
    if state.is_empty():
        return {"passed": False, "reason": "state пуст"}
    observed = state.filter(~pl.col("interpolated"))
    tol = EDGE_TOLERANCE_M
    inside = observed.filter(
        pl.col("x_m").is_between(-tol, length_m + tol) & pl.col("y_m").is_between(-tol, width_m + tol)
    )
    inside_share = len(inside) / len(observed) if len(observed) else 0.0
    max_speed = float(state["speed"].max())
    speed_ok = max_speed <= MAX_SPEED_MS
    inside_ok = inside_share >= MIN_INSIDE_SHARE
    return {
        "passed": speed_ok and inside_ok,
        "max_speed_ms": round(max_speed, 2),
        "speed_ok": speed_ok,
        "inside_share": round(inside_share, 4),
        "inside_ok": inside_ok,
        "fastest_track": int(state.sort("speed")["track_id"][-1]),
    }
