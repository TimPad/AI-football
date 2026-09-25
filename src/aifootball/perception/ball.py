"""L1/L2: фильтрация детекций мяча, интерполяция траектории и определение владения."""

import numpy as np
import polars as pl

MAX_BALL_SPEED_MS = 25.0  # ~90 км/ч — максимальная скорость удара в футзале
MAX_BALL_GAP_S = 1.5  # максимальный пропуск детекции мяча для интерполяции
POSSESSION_RADIUS_M = 1.8  # радиус контроля мяча игроком в метрах


def process_ball_trajectory(
    detections: pl.DataFrame,
    venue,
) -> pl.DataFrame:
    """Фильтрует детекции мяча, проецирует в метры и интерполирует пропуски.

    Возвращает DataFrame: frame_id, ts, x_m, y_m, speed, interpolated.
    """
    if detections.is_empty() or venue.H is None:
        return _empty_ball_df()

    from aifootball.geometry.homography import apply_homography
    from aifootball.geometry.polygons import points_in_polygon
    from aifootball.geometry.undistort import undistort_points

    balls = detections.filter(pl.col("cls") == "ball").sort("frame_id")
    if balls.is_empty():
        return _empty_ball_df()

    # Центр бокса мяча
    center_x = ((balls["x1"] + balls["x2"]) / 2).to_numpy()
    center_y = ((balls["y1"] + balls["y2"]) / 2).to_numpy()
    center_px = np.column_stack([center_x, center_y])

    # Проверка на нахождение мяча в границах поля
    in_pitch = points_in_polygon(center_px, venue.require_polygon())
    balls = balls.with_columns(in_pitch=pl.Series(in_pitch))
    balls = balls.filter(pl.col("in_pitch"))

    if balls.is_empty():
        return _empty_ball_df()

    px = np.column_stack([
        ((balls["x1"] + balls["x2"]) / 2).to_numpy(),
        ((balls["y1"] + balls["y2"]) / 2).to_numpy(),
    ])
    meters = apply_homography(venue.H, undistort_points(px, venue.calib))

    ts = balls["ts"].to_numpy()
    frame_ids = balls["frame_id"].to_numpy()
    x_m = meters[:, 0]
    y_m = meters[:, 1]

    # Фильтрация спайков (нефизичные прыжки мяча)
    clean_ts, clean_x, clean_y, clean_f = _filter_ball_spikes(ts, x_m, y_m, frame_ids)
    if len(clean_ts) == 0:
        return _empty_ball_df()

    # Линейная интерполяция коротких пропусков
    ts_interp, x_interp, y_interp, f_interp, is_interp = _interpolate_ball_gaps(
        clean_ts, clean_x, clean_y, clean_f
    )

    # Вычисление скорости
    vx = np.gradient(x_interp, ts_interp) if len(ts_interp) > 1 else np.zeros_like(x_interp)
    vy = np.gradient(y_interp, ts_interp) if len(ts_interp) > 1 else np.zeros_like(y_interp)
    speed = np.hypot(vx, vy)

    return pl.DataFrame({
        "frame_id": f_interp,
        "ts": ts_interp,
        "x_m": x_interp,
        "y_m": y_interp,
        "speed": speed,
        "interpolated": is_interp,
    })


def compute_possession(
    ball_state: pl.DataFrame,
    player_state: pl.DataFrame,
    possession_radius_m: float = POSSESSION_RADIUS_M,
) -> dict:
    """Вычисляет статистику владения мячом по командам."""
    if ball_state.is_empty() or player_state.is_empty():
        return {"possession_s": {"A": 0.0, "B": 0.0, "loose": 0.0}, "possession_pct": {"A": 0.0, "B": 0.0}}

    # Объединяем позиции мяча и игроков по кадрам
    joined = ball_state.join(player_state, on="frame_id", suffix="_player")
    if joined.is_empty():
        return {"possession_s": {"A": 0.0, "B": 0.0, "loose": 0.0}, "possession_pct": {"A": 0.0, "B": 0.0}}

    dx = joined["x_m"].to_numpy() - joined["x_m_player"].to_numpy()
    dy = joined["y_m"].to_numpy() - joined["y_m_player"].to_numpy()
    dist = np.hypot(dx, dy)

    joined = joined.with_columns(dist=pl.Series(dist))

    # Находим ближайшего игрока к мячу на каждом кадре
    nearest = (
        joined.filter(pl.col("dist") <= possession_radius_m)
        .sort("dist")
        .group_by("frame_id")
        .first()
    )

    if nearest.is_empty():
        return {"possession_s": {"A": 0.0, "B": 0.0, "loose": 0.0}, "possession_pct": {"A": 0.0, "B": 0.0}}

    # Подсчет времени владения мячом
    sample_step = float(np.median(np.diff(ball_state["ts"].to_numpy()))) if len(ball_state) > 1 else 0.1

    poss_a_frames = len(nearest.filter(pl.col("team") == "A"))
    poss_b_frames = len(nearest.filter(pl.col("team") == "B"))
    total_frames = max(1, poss_a_frames + poss_b_frames)

    poss_a_s = round(poss_a_frames * sample_step, 1)
    poss_b_s = round(poss_b_frames * sample_step, 1)
    loose_s = round((len(ball_state["frame_id"].unique()) - (poss_a_frames + poss_b_frames)) * sample_step, 1)

    pct_a = round(poss_a_frames / total_frames * 100, 1)
    pct_b = round(poss_b_frames / total_frames * 100, 1)

    return {
        "possession_s": {"A": poss_a_s, "B": poss_b_s, "loose": max(0.0, loose_s)},
        "possession_pct": {"A": pct_a, "B": pct_b},
    }


def _filter_ball_spikes(ts, x, y, frame_ids):
    if len(ts) < 2:
        return ts, x, y, frame_ids

    keep = [True] * len(ts)
    for i in range(1, len(ts)):
        dt = ts[i] - ts[i - 1]
        if dt <= 0:
            keep[i] = False
            continue
        dist = np.hypot(x[i] - x[i - 1], y[i] - y[i - 1])
        if dist / dt > MAX_BALL_SPEED_MS:
            keep[i] = False

    keep = np.array(keep, dtype=bool)
    return ts[keep], x[keep], y[keep], frame_ids[keep]


def _interpolate_ball_gaps(ts, x, y, frame_ids):
    if len(ts) < 2:
        return ts, x, y, frame_ids, np.zeros(len(ts), dtype=bool)

    step = float(np.median(np.diff(ts)))
    if step <= 0:
        step = 0.1

    out_ts, out_x, out_y, out_f, out_i = [ts[0]], [x[0]], [y[0]], [frame_ids[0]], [False]
    for i in range(1, len(ts)):
        dt = ts[i] - ts[i - 1]
        if 1.5 * step < dt <= MAX_BALL_GAP_S:
            missing = int(round(dt / step)) - 1
            for k in range(1, missing + 1):
                w = k / (missing + 1)
                out_ts.append(ts[i - 1] + w * dt)
                out_x.append(x[i - 1] + w * (x[i] - x[i - 1]))
                out_y.append(y[i - 1] + w * (y[i] - y[i - 1]))
                out_f.append(int(round(frame_ids[i - 1] + w * (frame_ids[i] - frame_ids[i - 1]))))
                out_i.append(True)
        out_ts.append(ts[i])
        out_x.append(x[i])
        out_y.append(y[i])
        out_f.append(frame_ids[i])
        out_i.append(False)

    return (
        np.array(out_ts),
        np.array(out_x),
        np.array(out_y),
        np.array(out_f, dtype=np.int32),
        np.array(out_i, dtype=bool),
    )


def _empty_ball_df() -> pl.DataFrame:
    return pl.DataFrame({
        "frame_id": pl.Series([], dtype=pl.Int32),
        "ts": pl.Series([], dtype=pl.Float64),
        "x_m": pl.Series([], dtype=pl.Float32),
        "y_m": pl.Series([], dtype=pl.Float32),
        "speed": pl.Series([], dtype=pl.Float32),
        "interpolated": pl.Series([], dtype=pl.Boolean),
    })
