"""События матча из траектории мяча и позиций игроков: передачи, потери, возвраты, ведение, удары.

Основа — владелец мяча по кадрам (perception.ball.ball_owners). Между двумя отрезками владения
мяч летит: своему — передача, сопернику — потеря и возврат, к воротам с большой скоростью — удар.
События ссылаются на трек и время видео; личность игрока здесь неизвестна.
В остановках игры (аут, фол, гол) игроки перекатывают мяч — такие «передачи» отбрасываются (stoppages).
"""
import numpy as np
import polars as pl

from aifootball.analytics.stoppage_model import stoppage_spans
from aifootball.perception.ball import MAX_PASS_FLIGHT_S, MIN_RUN_S, ball_owners

TEAMS = ("A", "B")
GOAL_HALF_M = 1.5           # ворота футзала 3 м
SHOT_MARGIN_M = 1.5         # «рядом с воротами» — до 1.5 м за штангой
SHOT_SPEED_MS = 9.0         # пас в футзале обычно медленнее; удар — быстрее
SHOT_MAX_DIST_M = 20.0      # дальше удары почти не наносят
SHOT_WINDOW_S = 1.2         # полёт мяча после удара, который анализируем
CARRY_MIN_M = 3.0
DUEL_RADIUS_M = 1.5
BLOCK_MAX_S = 1.0
# Остановки: полевые ходят медленнее обычного для этого матча, кто-то стоит у линии (ввод мяча).
# Пороги — доли медианной скорости матча, чтобы не зависеть от уровня игры. По двум журналам
# Ярославля: найдено ~половина времени остановок при точности ~0.88, точность передач 0.69 → 0.78;
# пороги 0.5–0.65 / 0.85–1.0 дают то же.
STOP_SLOW = 0.6
STOP_FAST = 0.9
STOP_LINE_WEIGHT = 1.5
STOP_SWITCH = 15.0          # цена смены «игра/остановка»: секундные колебания темпа не переключают
STOP_SMOOTH_S = 1.0
STOP_MIN_SPEED_MS = 0.3     # медиана ниже — скоростей нет (синтетика, статичная запись), остановки не ищем


def owner_runs(owners: pl.DataFrame, players: pl.DataFrame) -> list[dict]:
    """Отрезки владения одним игроком: трек, команда, начало/конец и позиции игрока."""
    if owners.is_empty():
        return []
    runs = (owners.with_columns(run=(pl.col("track_id") != pl.col("track_id").shift(1)).fill_null(True).cum_sum())
            .group_by("run", maintain_order=True)
            .agg(pl.col("track_id").first(), pl.col("team").first(), ts_start=pl.col("ts").min(), ts_end=pl.col("ts").max(),
                 frame_start=pl.col("frame_id").min(), frame_end=pl.col("frame_id").max()).to_dicts())
    pos = {(r["frame_id"], r["track_id"]): (r["x_m"], r["y_m"], r["role"])
           for r in players.select("frame_id", "track_id", "x_m", "y_m", "role").iter_rows(named=True)}
    runs = [r for r in runs if r["ts_end"] - r["ts_start"] >= MIN_RUN_S]
    for r in runs:
        r["xy_start"] = pos.get((r["frame_start"], r["track_id"]), (None, None, None))[:2]
        r["xy_end"] = pos.get((r["frame_end"], r["track_id"]), (None, None, None))[:2]
        r["role"] = pos.get((r["frame_end"], r["track_id"]), (None, None, None))[2]
    return runs


def stoppages(players: pl.DataFrame, length_m: float, width_m: float,
              ball: pl.DataFrame | None = None) -> list[tuple[float, float]]:
    """Отрезки остановок игры [начало, конец]: посекундный классификатор (analytics.stoppage_model) поверх Витерби.

    Один Витерби на двух залах: верно 0.70 и 0.66 секунд, остановок ловит 41–56%; классификатор — см. stoppage_model.
    """
    if "speed" not in players.columns:
        return []
    return stoppage_spans(players, ball, length_m, width_m, viterbi_stoppages(players, length_m, width_m))


def viterbi_stoppages(players: pl.DataFrame, length_m: float, width_m: float) -> list[tuple[float, float]]:
    """Отрезки остановок игры [начало, конец] по темпу полевых и игрокам у линии; Витерби на два состояния."""
    from aifootball.processor.candidates import restart_candidates

    if "speed" not in players.columns:
        return []
    field = players.filter((pl.col("role") == "player") & pl.col("team").is_in(TEAMS))
    if field.is_empty():
        return []
    tempo = field.group_by("frame_id").agg(pl.col("ts").first(), v=pl.col("speed").mean()).sort("frame_id")
    ts = tempo["ts"].to_numpy()
    step = float(np.median(np.diff(ts))) if len(ts) > 1 else 0.1
    v = tempo["v"].rolling_mean(max(1, round(STOP_SMOOTH_S / step)), center=True, min_samples=1).to_numpy()
    usual = float(np.median(v))
    if usual < STOP_MIN_SPEED_MS:
        return []
    at_line = np.zeros(len(ts), dtype=bool)
    for c in restart_candidates(players, length_m, width_m):
        at_line |= (ts >= c["start_s"]) & (ts <= c["end_s"])
    slow, fast = STOP_SLOW * usual, STOP_FAST * usual
    z = np.clip((v - slow) / (fast - slow), 0.0, 1.0)  # 0 — «стоят», 1 — «играют»
    cost = np.column_stack([1 - z + STOP_LINE_WEIGHT * at_line, z - STOP_LINE_WEIGHT * at_line])  # [игра, остановка]
    total, back = cost[0].copy(), np.zeros((len(ts), 2), dtype=int)
    for i in range(1, len(ts)):
        switched = total[::-1] + STOP_SWITCH
        back[i] = np.where(total <= switched, [0, 1], [1, 0])
        total = np.minimum(total, switched) + cost[i]
    state, path = int(np.argmin(total)), np.zeros(len(ts), dtype=int)
    for i in range(len(ts) - 1, -1, -1):
        path[i] = state
        state = back[i][state]
    spans, start = [], None
    for t, stopped in zip(ts, path):
        if stopped and start is None:
            start = t
        elif not stopped and start is not None:
            spans.append((float(start), float(t)))
            start = None
    if start is not None:
        spans.append((float(start), float(ts[-1])))
    return spans


def _flight(ball: pl.DataFrame, t0: float, t1: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    seg = ball.filter((pl.col("ts") >= t0) & (pl.col("ts") <= t1)).sort("ts")
    return seg["ts"].to_numpy(), seg["x_m"].to_numpy(), seg["y_m"].to_numpy()


def _shot(ball, run, next_run, length_m, width_m, attack_x):
    """Удар: быстрый полёт после отрезка владения в сторону атакуемых ворот, в створ или рядом."""
    t, x, y = _flight(ball, run["ts_end"], run["ts_end"] + SHOT_WINDOW_S)
    if len(t) < 3:
        return None
    dt = np.diff(t); step = np.hypot(np.diff(x), np.diff(y)) / np.maximum(dt, 1e-3)
    peak = float(np.max(step[: max(1, min(len(step), 8))]))
    if peak < SHOT_SPEED_MS:
        return None
    goals = [attack_x] if attack_x is not None else [0.0, length_m]
    for gx in goals:
        dx = gx - x[0]
        if abs(dx) > SHOT_MAX_DIST_M:
            continue
        # Направление по самой дальней точке полёта, чтобы шум первых кадров не решал.
        far = int(np.argmax(np.abs(x - x[0])))
        vx, vy = x[far] - x[0], y[far] - y[0]
        if vx == 0 or np.sign(vx) != np.sign(dx):
            continue
        y_goal = y[0] + vy * dx / vx
        miss = abs(y_goal - width_m / 2) - GOAL_HALF_M
        if miss > SHOT_MARGIN_M:
            continue
        on_target = bool(miss <= 0)
        outcome = "unknown"
        if next_run and next_run["team"] != run["team"] and next_run["ts_start"] - run["ts_end"] <= BLOCK_MAX_S:
            outcome = "saved" if next_run.get("role") == "goalkeeper" and on_target else "failure" if next_run.get("role") != "goalkeeper" else "unknown"
        elif not on_target:
            outcome = "off_target"
        blocked = outcome == "failure"
        return {"on_target": None if blocked else on_target, "outcome": outcome, "blocked": blocked,
                "speed_ms": round(peak, 1), "target_x": gx, "y_at_goal": round(float(y_goal), 2),
                "confidence": round(min(1.0, 0.5 + (peak - SHOT_SPEED_MS) / 20 + (0.2 if on_target else 0)), 2)}
    return None


def pass_counts(ball: pl.DataFrame, players: pl.DataFrame, length_m: float, width_m: float) -> dict:
    """Передачи по командам из тех же событий, что публикует сервис: без остановок, ударов и единоборств.

    Формат — как у perception.ball.detect_passes: passes_total, passes_completed, pass_accuracy_pct.
    """
    from aifootball.perception.teams import defending_sides

    sides = defending_sides(players)
    attack = {sides[0]: length_m, sides[1]: 0.0} if sides else None
    total, completed = {t: 0 for t in TEAMS}, {t: 0 for t in TEAMS}
    for e in extract_events(ball, players, length_m, width_m, attack):
        if e["kind"] == "pass" and e["team"] in TEAMS:
            total[e["team"]] += 1
            completed[e["team"]] += bool(e["success"])
    return {"passes_total": total, "passes_completed": completed,
            "pass_accuracy_pct": {t: round(completed[t] / total[t] * 100, 1) if total[t] else 0.0 for t in TEAMS}}


def extract_events(ball: pl.DataFrame, players: pl.DataFrame, length_m: float, width_m: float,
                   attack_x: dict[str, float] | None = None, skip_stoppages: bool = True) -> list[dict]:
    """Список событий по времени. attack_x — x атакуемых ворот для команд A/B, если известен.

    Вратарям в players уже должна быть назначена команда по воротам (report_data.assign_goalkeeper_teams).
    """
    owners = ball_owners(ball, players)
    runs = owner_runs(owners, players)
    events: list[dict] = []
    near = players.filter(pl.col("team").is_in(TEAMS)).select("frame_id", "track_id", "team", "x_m", "y_m")
    ball_at = {r["frame_id"]: (r["x_m"], r["y_m"]) for r in ball.select("frame_id", "x_m", "y_m").iter_rows(named=True)}
    for i, run in enumerate(runs):
        nxt = runs[i + 1] if i + 1 < len(runs) else None
        base = {"track_id": run["track_id"], "team": run["team"], "start_s": run["ts_end"], "start_xy": run["xy_end"]}
        if run["xy_start"][0] is not None and run["xy_end"][0] is not None:
            moved = float(np.hypot(run["xy_end"][0] - run["xy_start"][0], run["xy_end"][1] - run["xy_start"][1]))
            if moved >= CARRY_MIN_M:
                events.append({"kind": "carry", "track_id": run["track_id"], "team": run["team"], "start_s": run["ts_start"],
                               "end_s": run["ts_end"], "start_xy": run["xy_start"], "end_xy": run["xy_end"],
                               "success": None if nxt is None else nxt["team"] == run["team"], "confidence": 0.6})
        shot = _shot(ball, run, nxt, length_m, width_m, (attack_x or {}).get(run["team"]))
        if shot:
            events.append({"kind": "shot", **base, **shot})
            if shot["blocked"] and nxt:
                events.append({"kind": "shot_block", "track_id": nxt["track_id"], "team": nxt["team"], "start_s": nxt["ts_start"],
                               "start_xy": nxt["xy_start"], "confidence": shot["confidence"]})
            elif shot["outcome"] == "saved" and nxt:
                events.append({"kind": "save", "track_id": nxt["track_id"], "team": nxt["team"], "start_s": nxt["ts_start"],
                               "start_xy": nxt["xy_start"], "confidence": shot["confidence"]})
            continue
        if nxt is None or nxt["ts_start"] - run["ts_end"] > MAX_PASS_FLIGHT_S:
            continue
        if nxt["team"] == run["team"]:
            if nxt["track_id"] != run["track_id"]:
                events.append({"kind": "pass", **base, "end_s": nxt["ts_start"], "end_xy": nxt["xy_start"],
                               "recipient_track_id": nxt["track_id"], "success": True, "confidence": 0.7})
            continue
        # Мяч перешёл сопернику: близкий контакт — единоборство, иначе неточная передача.
        frame = nxt["frame_start"]; bxy = ball_at.get(frame)
        duel = False
        if bxy is not None:
            close = near.filter((pl.col("frame_id") == frame) & (pl.col("track_id") == run["track_id"]))
            if close.height:
                duel = float(np.hypot(close["x_m"][0] - bxy[0], close["y_m"][0] - bxy[1])) <= DUEL_RADIUS_M
        if duel:
            events.append({"kind": "duel", "track_id": nxt["track_id"], "team": nxt["team"], "start_s": nxt["ts_start"],
                           "start_xy": nxt["xy_start"], "opponent_track_id": run["track_id"], "success": True, "confidence": 0.5})
            events.append({"kind": "duel", **base, "opponent_track_id": nxt["track_id"], "success": False, "confidence": 0.5})
        else:
            events.append({"kind": "pass", **base, "end_s": nxt["ts_start"], "end_xy": nxt["xy_start"],
                           "recipient_track_id": None, "success": False, "confidence": 0.6})
        events.append({"kind": "turnover", **base, "confidence": 0.6})
        events.append({"kind": "recovery", "track_id": nxt["track_id"], "team": nxt["team"], "start_s": nxt["ts_start"],
                       "start_xy": nxt["xy_start"], "confidence": 0.6})
    if skip_stoppages:
        spans = stoppages(players, length_m, width_m, ball)
        stopped = lambda t: t is not None and any(a <= t <= b for a, b in spans)
        events = [e for e in events if not stopped(e["start_s"]) and not stopped(e.get("end_s"))]
    return sorted(events, key=lambda e: (e["start_s"], e["kind"]))
