"""Цифры отчёта по матчу: обзор команд, трети, тепловые карты, ход матча, игроки, моменты.

Только данные — никакого HTML. Всё считается внутри периода (весь матч / тайм).
Спецификация: docs/specs/2026-10-13-match-report-design.md.
"""

import numpy as np

import polars as pl

from aifootball.state.smooth import MAX_GAP_S

from aifootball.analytics.periods import in_period

from aifootball.perception.teams import defending_sides

from aifootball.analytics.metrics import HEATMAP_CELL_M, compute_metrics

from aifootball.analytics.metrics import SPRINT_MIN_DURATION_S, SPRINT_THRESHOLD_MS

import cv2

from aifootball.analytics.periods import make_periods

HSR_MS = 4.0  # бег быстрее этого — «высокоинтенсивный»; стартовое значение, см. спецификацию

SUSTAIN_S = 0.5  # устойчивая скорость: медиана за это окно, одиночные пики не в счёт

TEAMS = ("A", "B")

SERIES_BIN_S = 300.0  # ход матча по 5-минутным отрезкам

LOW_DATA_SHARE = 0.5  # меньше половины от «период × 4 полевых» — пометка «мало данных»

FIELD_PLAYERS = 4

MIN_PLAYER_S = 60.0  # трек короче — только в командных суммах, в таблице игроков его нет

BUSY_WINDOW_S = 60.0  # «самая беговая минута»

FALLBACK_COLORS = {"A": "#1fae4b", "B": "#f07a1a"}

MIN_COLOR_DIST = 30.0  # цвета формы ближе — неразличимы на полосках, берём зелёный и оранжевый


def segments(ts: np.ndarray) -> list[slice]:
    """Непрерывные куски трека: разрыв больше MAX_GAP_S начинает новый."""
    if len(ts) == 0:
        return []
    cuts = (np.flatnonzero(np.diff(ts) > MAX_GAP_S) + 1).tolist()
    bounds = [0, *cuts, len(ts)]
    return [slice(a, b) for a, b in zip(bounds, bounds[1:])]

def hsr_distance(ts: np.ndarray, x: np.ndarray, y: np.ndarray, speed: np.ndarray) -> float:
    """Метры на шагах, где скорость в конце шага выше HSR_MS (через разрыв трека не считаем)."""
    if len(ts) < 2:
        return 0.0
    steps = np.hypot(np.diff(x), np.diff(y))
    fast = (np.diff(ts) <= MAX_GAP_S) & (speed[1:] > HSR_MS)
    return round(float(steps[fast].sum()), 2)

def sustained_speeds(ts: np.ndarray, speed: np.ndarray, cap: float) -> tuple[np.ndarray, np.ndarray]:
    """(время середины окна, медиана скорости за SUSTAIN_S); окна на пределе фильтра cap выброшены."""
    if len(ts) < 2:
        return np.array([]), np.array([])
    step = float(np.median(np.diff(ts)))
    n = max(1, int(round(SUSTAIN_S / step))) if step > 0 else 1
    times, values = [], []
    for seg in segments(ts):
        s, t = speed[seg], ts[seg]
        if len(s) < n:
            continue
        med = np.median(np.lib.stride_tricks.sliding_window_view(s, n), axis=1)
        mid = np.lib.stride_tricks.sliding_window_view(t, n)[:, n // 2]
        keep = med < cap - 1e-3
        times.append(mid[keep])
        values.append(med[keep])
    if not values:
        return np.array([]), np.array([])
    return np.concatenate(times), np.concatenate(values)

def sustained_max_speed(ts: np.ndarray, speed: np.ndarray, cap: float) -> float | None:
    _, values = sustained_speeds(ts, speed, cap)
    return round(float(values.max()), 2) if values.size else None

def assign_goalkeeper_teams(state: pl.DataFrame, spans, length_m: float) -> pl.DataFrame:
    """Команда вратаря в каждом тайме — защищающая ворота, у которых он стоит (команды меняются воротами)."""
    parts = []
    for span in spans:
        part = in_period(state, [span])
        sides = defending_sides(part)
        if sides is None:
            parts.append(part)
            continue
        left, right = sides
        keeper_pos = part.filter(pl.col("role") == "goalkeeper").group_by("track_id").agg(
            keeper_x=pl.col("x_m").median())
        parts.append(part.join(keeper_pos, on="track_id", how="left").with_columns(
            team=pl.when(pl.col("role") != "goalkeeper").then(pl.col("team"))
            .when(pl.col("keeper_x") < length_m / 2).then(pl.lit(left)).otherwise(pl.lit(right))
        ).drop("keeper_x"))
    return pl.concat(parts) if parts else state.clear()

def orient(state: pl.DataFrame, spans, length_m: float, width_m: float | None = None) -> tuple[pl.DataFrame, bool]:
    """Поворачивает поле так, чтобы свои ворота каждой команды были слева (x = 0) в каждом тайме.

    Возвращает (повёрнутые строки, удалось ли определить направление во всех таймах).
    """
    parts, ok = [], True
    for span in spans:
        part = in_period(state, [span])
        has_both = part.filter((pl.col("role") == "player") & pl.col("team").is_in(TEAMS))["team"].n_unique() == 2
        if not has_both or defending_sides(part) is None:
            ok = False
            parts.append(part)
            continue
        left, _ = defending_sides(part)
        coords = {"x_m": pl.when(pl.col("team") == left).then(pl.col("x_m")).otherwise(length_m - pl.col("x_m"))}
        if width_m is not None:
            coords["y_m"] = pl.when(pl.col("team") == left).then(pl.col("y_m")).otherwise(width_m - pl.col("y_m"))
        parts.append(part.with_columns(**coords))
    return (pl.concat(parts) if parts else state.clear()), ok

def thirds_share(oriented: pl.DataFrame, length_m: float) -> dict:
    """Проценты времени, когда центр команды в своей / средней / чужой трети (свои ворота слева)."""
    out = {}
    for team in TEAMS:
        centers = (
            oriented.filter((pl.col("role") == "player") & (pl.col("team") == team))
            .group_by("frame_id").agg(x=pl.col("x_m").mean(), n=pl.len())
            .filter(pl.col("n") >= 2)["x"].to_numpy()
        )
        if centers.size == 0:
            out[team] = None
            continue
        idx = np.clip((centers / (length_m / 3)).astype(int), 0, 2)
        counts = np.bincount(idx, minlength=3)
        exact = counts / counts.sum() * 100
        shares = np.floor(exact).astype(int)
        for k in np.argsort(-(exact - shares), kind="stable")[:100 - int(shares.sum())]:
            shares[k] += 1
        out[team] = shares.tolist()
    return out

def team_overview(state: pl.DataFrame, oriented: pl.DataFrame, length_m: float, width_m: float,
                  cap: float, period_s: float) -> dict:
    """Строки сравнения команд по полевым игрокам; тепловая карта — по повёрнутому полю."""
    field = state.filter(pl.col("role") == "player")
    metrics = compute_metrics(field, length_m, width_m)
    oriented_field = oriented.filter(pl.col("role") == "player")
    out = {}
    for team in TEAMS:
        t = metrics["teams"][team]
        g = field.filter(pl.col("team") == team).sort("track_id", "ts")
        hsr = sum(
            hsr_distance(tr["ts"].to_numpy(), tr["x_m"].to_numpy(), tr["y_m"].to_numpy(), tr["speed"].to_numpy())
            for _, tr in g.group_by("track_id", maintain_order=True)
        )
        width, depth = _shape(g)
        observed = t["observed_s"]
        out[team] = {
            "distance_m": t["distance_m"],
            "m_per_min": round(t["distance_m"] / observed * 60, 1) if observed > 0 else 0.0,
            "hsr_m": round(hsr, 1),
            "sprints": t["sprints_count"],
            "compactness_m2": t["compactness_m2"],
            "width_m": width,
            "depth_m": depth,
            "observed_s": observed,
            "low_data": bool(observed < LOW_DATA_SHARE * FIELD_PLAYERS * period_s),
            "heatmap_s": heatmap_seconds(oriented_field.filter(pl.col("team") == team), length_m, width_m),
        }
    return out

def _shape(team_state: pl.DataFrame) -> tuple[float, float]:
    """(ширина поперёк поля, глубина вдоль поля) — средний размах по кадрам, где ≥ 3 игрока команды."""
    per = (
        team_state.group_by("frame_id")
        .agg(n=pl.len(), dx=pl.col("x_m").max() - pl.col("x_m").min(), dy=pl.col("y_m").max() - pl.col("y_m").min())
        .filter(pl.col("n") >= 3)
    )
    if per.is_empty():
        return 0.0, 0.0
    return round(float(per["dy"].mean()), 1), round(float(per["dx"].mean()), 1)

def _steps(state: pl.DataFrame) -> pl.DataFrame:
    """Шаги треков: ts конца шага, команда, длина шага, dt; через разрыв трека шагов нет."""
    return (
        state.sort("track_id", "ts")
        .with_columns(
            dt=pl.col("ts").diff().over("track_id"),
            step=(pl.col("x_m").diff().over("track_id") ** 2 + pl.col("y_m").diff().over("track_id") ** 2).sqrt(),
        )
        .filter(pl.col("dt").is_not_null() & (pl.col("dt") <= MAX_GAP_S))
    )

def series(state: pl.DataFrame, spans) -> dict:
    """Метров в минуту на полевого игрока по отрезкам SERIES_BIN_S; start_min — от начала периода."""
    steps = _steps(state.filter(pl.col("role") == "player"))
    out = {"bin_s": SERIES_BIN_S, "start_min": [], "A": [], "B": []}
    offset = 0.0
    for start, end in spans:
        for b0 in np.arange(start, end, SERIES_BIN_S):
            chunk = steps.filter((pl.col("ts") >= b0) & (pl.col("ts") < min(b0 + SERIES_BIN_S, end)))
            out["start_min"].append(round((offset + b0 - start) / 60, 1))
            for team in TEAMS:
                c = chunk.filter(pl.col("team") == team)
                observed = float(c["dt"].sum())
                out[team].append(round(float(c["step"].sum()) / observed * 60, 1) if observed > 0 else None)
        offset += end - start
    return out

def _observed(state: pl.DataFrame) -> pl.DataFrame:
    """По треку: секунды наблюдения, первое появление, команда (чаще всего), роль."""
    return (
        _steps(state).group_by("track_id").agg(observed_s=pl.col("dt").sum())
        .join(state.group_by("track_id").agg(
            first_ts=pl.col("ts").min(), team=pl.col("team").mode().first(), role=pl.col("role").first()),
            on="track_id")
    )

def player_labels(state: pl.DataFrame, min_s: float = MIN_PLAYER_S) -> dict[int, str]:
    """Имена строк таблицы: «Игрок N» по порядку появления внутри команды, «Вратарь», «Вратарь 2»…"""
    obs = _observed(state.filter(pl.col("role").is_in(["player", "goalkeeper"]) & pl.col("team").is_in(TEAMS)))
    labels, players, keepers = {}, {t: 0 for t in TEAMS}, {t: 0 for t in TEAMS}
    for row in obs.filter(pl.col("observed_s") >= min_s).sort("first_ts", "track_id").iter_rows(named=True):
        team = row["team"]
        if row["role"] == "goalkeeper":
            keepers[team] += 1
            labels[row["track_id"]] = "Вратарь" if keepers[team] == 1 else f"Вратарь {keepers[team]}"
        else:
            players[team] += 1
            labels[row["track_id"]] = f"Игрок {players[team]}"
    return labels

def players_table(state: pl.DataFrame, oriented: pl.DataFrame, labels: dict[int, str],
                  length_m: float, width_m: float, cap: float) -> list[dict]:
    """Строки таблицы игроков периода: треки из labels, наблюдавшиеся в периоде ≥ MIN_PLAYER_S."""
    metrics = compute_metrics(state, length_m, width_m)["tracks"]
    rows = []
    for track_id, label in labels.items():
        m = metrics.get(str(track_id))
        if m is None or m["observed_s"] < MIN_PLAYER_S:
            continue
        g = state.filter(pl.col("track_id") == track_id).sort("ts")
        ts, speed = g["ts"].to_numpy(), g["speed"].to_numpy()
        rows.append({
            "track_id": track_id,
            "label": label,
            "team": g["team"].mode().first(),
            "role": m["role"],
            "observed_s": m["observed_s"],
            "distance_m": m["distance_m"],
            "m_per_min": m["distance_per_min"],
            "hsr_m": hsr_distance(ts, g["x_m"].to_numpy(), g["y_m"].to_numpy(), speed),
            "sprints": m["sprints_count"],
            "vmax_ms": sustained_max_speed(ts, speed, cap),
            "heatmap_s": heatmap_seconds(oriented.filter(pl.col("track_id") == track_id), length_m, width_m),
        })
    return sorted(rows, key=lambda r: (r["team"], r["role"] != "player", -r["observed_s"]))

def thumb_request(tracks: pl.DataFrame, track_id: int) -> dict | None:
    """Кадр для миниатюры: середина самого длинного непрерывного куска трека на поле."""
    g = tracks.filter((pl.col("track_id") == track_id) & pl.col("in_pitch")).sort("ts")
    if g.is_empty():
        return None
    longest = max(segments(g["ts"].to_numpy()), key=lambda s: s.stop - s.start)
    row = g.row(longest.start + (longest.stop - longest.start) // 2, named=True)
    return {"kind": "thumb", "frame_id": row["frame_id"], "box": [row["x1"], row["y1"], row["x2"], row["y2"]]}

def _still(tracks: pl.DataFrame, ts: float, track_id: int | None) -> dict | None:
    """Стоп-кадр на момент ts; с track_id — с рамкой игрока."""
    if tracks.is_empty():
        return None
    if track_id is not None:
        g = tracks.filter(pl.col("track_id") == track_id)
        if not g.is_empty():
            row = g.with_columns(d=(pl.col("ts") - ts).abs()).sort("d").row(0, named=True)
            return {"kind": "still", "frame_id": row["frame_id"], "box": [row["x1"], row["y1"], row["x2"], row["y2"]]}
    row = tracks.with_columns(d=(pl.col("ts") - ts).abs()).sort("d").row(0, named=True)
    return {"kind": "still", "frame_id": row["frame_id"], "box": None}

def moments(state: pl.DataFrame, tracks: pl.DataFrame, labels: dict[int, str], spans, cap: float) -> list[dict]:
    """Самый длинный спринт, самая высокая устойчивая скорость, самая беговая минута каждой команды."""
    found = []
    best_sprint, best_speed = None, None
    for (track_id,), g in state.filter((pl.col("role") == "player") & pl.col("team").is_in(TEAMS)).sort("track_id", "ts").group_by(
            "track_id", maintain_order=True):
        ts, x, y, speed = (g[c].to_numpy() for c in ("ts", "x_m", "y_m", "speed"))
        team = g["team"].mode().first()
        for seg in segments(ts):
            fast = speed[seg] >= SPRINT_THRESHOLD_MS
            padded = np.concatenate([[0], fast.astype(int), [0]])
            edges = np.flatnonzero(np.diff(padded))
            for a, b in zip(edges[::2], edges[1::2]):
                i0, i1 = seg.start + a, seg.start + b
                if ts[i1 - 1] - ts[i0] < SPRINT_MIN_DURATION_S:
                    continue
                dist = float(np.hypot(np.diff(x[i0:i1]), np.diff(y[i0:i1])).sum())
                if best_sprint is None or dist > best_sprint[0]:
                    best_sprint = (dist, track_id, team, float(ts[i0]))
        times, values = sustained_speeds(ts, speed, cap)
        if values.size and (best_speed is None or values.max() > best_speed[0]):
            k = int(np.argmax(values))
            best_speed = (float(values[k]), track_id, team, float(times[k]))

    def label(track_id):
        return labels.get(track_id, f"трек {track_id}")

    if best_sprint:
        dist, track_id, team, ts0 = best_sprint
        found.append({"kind": "sprint", "title": "Самый длинный спринт", "value": f"{dist:.0f} м",
                      "ts": ts0, "team": team, "track_id": track_id, "label": label(track_id),
                      "still": _still(tracks, ts0, track_id)})
    if best_speed:
        v, track_id, team, ts0 = best_speed
        found.append({"kind": "speed", "title": "Самая высокая скорость", "value": f"{v:.1f} м/с",
                      "ts": ts0, "team": team, "track_id": track_id, "label": label(track_id),
                      "still": _still(tracks, ts0, track_id)})

    steps = _steps(state.filter(pl.col("role") == "player"))
    for team in TEAMS:
        per_s = (
            steps.filter(pl.col("team") == team)
            .with_columns(sec=pl.col("ts").floor())
            .group_by("sec").agg(step=pl.col("step").sum(), dt=pl.col("dt").sum())
        )
        best = None
        for start, end in spans:
            grid = pl.DataFrame({"sec": np.arange(np.floor(start), np.floor(end))}).join(per_s, on="sec", how="left").fill_null(0)
            n = int(BUSY_WINDOW_S)
            if grid.height < n:
                continue
            step_w = np.lib.stride_tricks.sliding_window_view(grid["step"].to_numpy(), n).sum(axis=1)
            dt_w = np.lib.stride_tricks.sliding_window_view(grid["dt"].to_numpy(), n).sum(axis=1)
            ok = dt_w >= 2 * BUSY_WINDOW_S  # в среднем хотя бы 2 игрока в кадре
            if not ok.any():
                continue
            rate = np.where(ok, step_w / np.maximum(dt_w, 1e-9) * 60, -1)
            k = int(np.argmax(rate))
            if best is None or rate[k] > best[0]:
                best = (float(rate[k]), float(grid["sec"][k]))
        if best:
            found.append({"kind": f"minute_{team}", "title": "Самая беговая минута", "value": f"{best[0]:.0f} м/мин",
                          "ts": best[1], "team": team, "track_id": None, "label": None,
                          "still": _still(tracks, best[1] + BUSY_WINDOW_S / 2, None)})
    return found

def team_colors(tracks: pl.DataFrame) -> dict[str, str]:
    """Цвет команды для полосок — медианный цвет формы, затемнённый для белого фона."""
    lab = {}
    for team in TEAMS:
        g = tracks.filter((pl.col("role") == "player") & (pl.col("team") == team) & pl.col("torso_a").is_not_nan())
        if g.is_empty():
            return dict(FALLBACK_COLORS)
        lab[team] = [float(g[c].median()) for c in ("torso_l", "torso_a", "torso_b")]
    if np.hypot(lab["A"][1] - lab["B"][1], lab["A"][2] - lab["B"][2]) < MIN_COLOR_DIST:
        return dict(FALLBACK_COLORS)
    out = {}
    for team, (l, a, b) in lab.items():
        bgr = cv2.cvtColor(np.uint8([[[min(l, 170.0), a, b]]]), cv2.COLOR_LAB2BGR)[0, 0]
        out[team] = "#{:02x}{:02x}{:02x}".format(int(bgr[2]), int(bgr[1]), int(bgr[0]))
    return out

def ball_summary(ball_state: pl.DataFrame, state: pl.DataFrame, length_m: float, width_m: float) -> dict:
    """Владение и передачи за период — только по --with-ball, с замеренной точностью. Передачи — как в events.json."""
    from aifootball.analytics.events import pass_counts
    from aifootball.perception.ball import compute_possession

    return {
        "possession": compute_possession(ball_state, state),
        "passes": pass_counts(ball_state, state, length_m, width_m),
        "caveat": "Приблизительно: по ручным журналам двух залов находится около двух третей передач, "
                  "из найденных верна примерно половина.",
    }

def build_report(state: pl.DataFrame, tracks: pl.DataFrame, venue, spans, team_names: dict,
                 video_s: float, ball_state: pl.DataFrame | None = None) -> dict:
    """Все цифры отчёта; venue нужен только для length_m, width_m, max_physical_speed."""
    length_m, width_m, cap = venue.length_m, venue.width_m, venue.max_physical_speed
    state = assign_goalkeeper_teams(in_period(state, spans), spans, length_m)
    labels = player_labels(state)
    thumbs = {str(tid): req for tid in labels if (req := thumb_request(tracks, tid)) is not None}

    periods = []
    for p in make_periods(spans):
        part = in_period(state, p.spans)
        oriented, oriented_ok = orient(part, p.spans, length_m, width_m)
        entry = {
            "key": p.key,
            "name": p.name,
            "spans": [list(s) for s in p.spans],
            "duration_s": round(p.duration_s, 1),
            "teams": team_overview(part, oriented, length_m, width_m, cap, p.duration_s),
            "thirds": thirds_share(oriented, length_m) if oriented_ok else {t: None for t in TEAMS},
            "series": series(part, p.spans),
            "players": players_table(part, oriented, labels, length_m, width_m, cap),
            "moments": moments(part, tracks, labels, p.spans, cap),
            "input_quality": input_quality(part, cap),
        }
        if ball_state is not None:
            entry["ball"] = ball_summary(in_period(ball_state, p.spans), part, length_m, width_m)
        periods.append(entry)

    return {
        "schema_version": "1",
        "match": {
            "teams": team_names,
            "colors": team_colors(tracks),
            "video_s": round(video_s, 1),
            "processed_s": round(_coverage_seconds(tracks, spans), 1),
            "halves_found": len(spans) == 2,
        },
        "pitch": {"length_m": length_m, "width_m": width_m, "cell_m": HEATMAP_CELL_M},
        "thumbs": thumbs,
        "periods": periods,
    }

def input_quality(state: pl.DataFrame, cap: float) -> dict:
    """Скачки координат выше физического предела, даже если столбец speed уже ограничен."""
    steps = _steps(state.filter((pl.col("role") == "player") & pl.col("team").is_in(TEAMS)))
    suspect = steps.filter((pl.col("dt") > 0) & (pl.col("step") / pl.col("dt") > cap + 0.1))
    return {"suspect_steps": suspect.height, "steps": steps.height}

def heatmap_seconds(state: pl.DataFrame, length_m: float, width_m: float) -> list[list[float]]:
    """Секунды наблюдения в клетках 1 × 1 м; длинные разрывы исключены."""
    grid = np.zeros((int(np.ceil(length_m)), int(np.ceil(width_m))))
    steps = _steps(state)
    if steps.is_empty():
        return grid.tolist()
    x = np.clip(steps["x_m"].to_numpy().astype(np.float64), 0, length_m - 1e-6).astype(int)
    y = np.clip(steps["y_m"].to_numpy().astype(np.float64), 0, width_m - 1e-6).astype(int)
    np.add.at(grid, (x, y), steps["dt"].to_numpy())
    return grid.round(2).tolist()

def _coverage_seconds(tracks: pl.DataFrame, spans) -> float:
    """Длительность имеющихся кадров внутри таймов, без пустых промежутков."""
    times = tracks["ts"].unique().sort().to_numpy()
    if not times.size:
        return 0.0
    diffs = np.diff(times)
    small = diffs[(diffs > 0) & (diffs <= MAX_GAP_S)]
    step = float(np.median(small)) if small.size else 0.0
    # Continuous frames cover their actual timestamp gaps, which can alternate
    # after sampling e.g. 14.9 fps down to 10 fps. A median-width box per frame
    # understates this coverage, and can double-count overlapping boxes.
    ends = np.r_[np.where(diffs <= MAX_GAP_S, times[1:], times[:-1] + step), times[-1] + step]
    return sum(float(np.maximum(0, np.minimum(ends, end) - np.maximum(times, start)).sum())
               for start, end in spans)
