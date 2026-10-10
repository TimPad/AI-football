"""Модуль расчета метрик качества (Фаза 2): Precision, Recall, IDF1, MOTA и ошибка проекции.

Все метрики рассчитываются с разбивкой по ближней и дальней половине поля. Ближняя —
та часть, где поле в кадре крупнее, чем в центре поля (масштаб по гомографии): так
деление не зависит от того, с какой стороны и под каким углом стоит камера.
"""

import math
import numpy as np
import polars as pl


def evaluate_detections(
    pred_df: pl.DataFrame,
    gt_df: pl.DataFrame,
    venue,
    iou_threshold: float = 0.5,
) -> dict:
    """Вычисляет Precision, Recall и F1-score детекций.

    Отдельно для ближней и дальней половины поля — по точке касания пола (низ бокса).
    """
    if gt_df.is_empty():
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "near_f1": 1.0, "far_f1": 1.0}

    overall = _eval_box_matches(pred_df, gt_df, iou_threshold)

    gt_is_near = pl.Series(_boxes_near_camera(gt_df, venue))
    pred_is_near = pl.Series(_boxes_near_camera(pred_df, venue))
    gt_near, gt_far = gt_df.filter(gt_is_near), gt_df.filter(~gt_is_near)
    pred_near, pred_far = pred_df.filter(pred_is_near), pred_df.filter(~pred_is_near)

    near = _eval_box_matches(pred_near, gt_near, iou_threshold)
    far = _eval_box_matches(pred_far, gt_far, iou_threshold)

    return {
        "precision": round(overall["precision"], 4),
        "recall": round(overall["recall"], 4),
        "f1": round(overall["f1"], 4),
        "near_half": {
            "precision": round(near["precision"], 4),
            "recall": round(near["recall"], 4),
            "f1": round(near["f1"], 4),
        },
        "far_half": {
            "precision": round(far["precision"], 4),
            "recall": round(far["recall"], 4),
            "f1": round(far["f1"], 4),
        },
    }


def evaluate_tracking(pred_df: pl.DataFrame, gt_df: pl.DataFrame) -> dict:
    """Вычисляет метрики качества трекинга: ID Swaps, IDF1, MOTA."""
    if gt_df.is_empty() or pred_df.is_empty():
        return {"id_swaps": 0, "idf1": 0.0, "mota": 0.0}

    # Подсчет переключений ID (ID Swaps)
    id_swaps = 0
    gt_frames = gt_df.select("frame_id", "track_id").unique()
    pred_frames = pred_df.select("frame_id", "track_id").unique()

    # Сопоставление треков по кадрам
    joined = gt_df.join(pred_df, on="frame_id", suffix="_pred")
    if joined.is_empty():
        return {"id_swaps": 0, "idf1": 0.0, "mota": 0.0}

    # Маппинг между GT track_id и PRED track_id
    last_mapping = {}
    for frame_id, gt_tid, pred_tid in joined.select("frame_id", "track_id", "track_id_pred").iter_rows():
        if gt_tid in last_mapping and last_mapping[gt_tid] != pred_tid:
            id_swaps += 1
        last_mapping[gt_tid] = pred_tid

    # Упрощенная оценка IDF1 и MOTA
    tp = len(joined)
    fp = max(0, len(pred_df) - tp)
    fn = max(0, len(gt_df) - tp)

    mota = max(0.0, 1.0 - (fn + fp + id_swaps) / max(1, len(gt_df)))
    idf1 = (2 * tp) / max(1, (2 * tp + fp + fn))

    return {
        "id_swaps": id_swaps,
        "idf1": round(float(idf1), 4),
        "mota": round(float(mota), 4),
    }


def evaluate_projection_error(
    pred_state: pl.DataFrame,
    gt_state: pl.DataFrame,
    venue,
) -> dict:
    """Вычисляет ошибку проекции в метрах (MAE и RMSE).

    Отдельно для ближней и дальней половины поля — по эталонной позиции.
    """
    if gt_state.is_empty() or pred_state.is_empty():
        return {"mae_m": 0.0, "rmse_m": 0.0, "near_half_mae_m": 0.0, "far_half_mae_m": 0.0}

    joined = gt_state.join(pred_state, on=["frame_id", "track_id"], suffix="_pred")
    if joined.is_empty():
        return {"mae_m": 0.0, "rmse_m": 0.0, "near_half_mae_m": 0.0, "far_half_mae_m": 0.0}

    dx = joined["x_m"].to_numpy() - joined["x_m_pred"].to_numpy()
    dy = joined["y_m"].to_numpy() - joined["y_m_pred"].to_numpy()
    dist = np.hypot(dx, dy)

    near_mask = near_camera(joined.select("x_m", "y_m").to_numpy(), venue)
    far_mask = ~near_mask

    mae = float(np.mean(dist))
    rmse = float(np.sqrt(np.mean(dist**2)))

    near_mae = float(np.mean(dist[near_mask])) if np.any(near_mask) else 0.0
    far_mae = float(np.mean(dist[far_mask])) if np.any(far_mask) else 0.0

    return {
        "mae_m": round(mae, 3),
        "rmse_m": round(rmse, 3),
        "near_half_mae_m": round(near_mae, 3),
        "far_half_mae_m": round(far_mae, 3),
    }


def near_camera(points_m: np.ndarray, venue) -> np.ndarray:
    """True для точек поля (в метрах), где поле в кадре крупнее, чем в его центре."""
    from aifootball.geometry.homography import pixels_per_meter

    center = pixels_per_meter(venue.H, np.array([[venue.length_m / 2, venue.width_m / 2]]))[0]
    return pixels_per_meter(venue.H, points_m) >= center


def _boxes_near_camera(boxes: pl.DataFrame, venue) -> np.ndarray:
    from aifootball.geometry.homography import apply_homography
    from aifootball.geometry.undistort import undistort_points

    if boxes.is_empty():
        return np.zeros(0, dtype=bool)
    feet = np.column_stack([((boxes["x1"] + boxes["x2"]) / 2).to_numpy(), boxes["y2"].to_numpy()])
    return near_camera(apply_homography(venue.H, undistort_points(feet.astype(float), venue.calib)), venue)


def _eval_box_matches(pred: pl.DataFrame, gt: pl.DataFrame, iou_thresh: float) -> dict:
    if gt.is_empty():
        return {"precision": 1.0 if pred.is_empty() else 0.0, "recall": 1.0, "f1": 1.0}
    if pred.is_empty():
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    tp, fp, fn = 0, 0, 0
    gt_by_frame = {k[0]: g for k, g in gt.partition_by("frame_id", as_dict=True).items()}
    pred_by_frame = {k[0]: g for k, g in pred.partition_by("frame_id", as_dict=True).items()}

    all_frames = set(gt_by_frame.keys()) | set(pred_by_frame.keys())
    for fid in all_frames:
        g_df = gt_by_frame.get(fid)
        p_df = pred_by_frame.get(fid)
        if g_df is None:
            fp += len(p_df)
            continue
        if p_df is None:
            fn += len(g_df)
            continue

        g_boxes = g_df.select("x1", "y1", "x2", "y2").to_numpy()
        p_boxes = p_df.select("x1", "y1", "x2", "y2").to_numpy()

        matched_gt = set()
        for p_box in p_boxes:
            best_iou = 0.0
            best_idx = -1
            for idx, g_box in enumerate(g_boxes):
                if idx in matched_gt:
                    continue
                iou = _box_iou(p_box, g_box)
                if iou > best_iou:
                    best_iou = iou
                    best_idx = idx
            if best_iou >= iou_thresh and best_idx >= 0:
                tp += 1
                matched_gt.add(best_idx)
            else:
                fp += 1
        fn += len(g_boxes) - len(matched_gt)

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
    return {"precision": prec, "recall": rec, "f1": f1}


def _box_iou(box1: np.ndarray, box2: np.ndarray) -> float:
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter_area <= 0:
        return 0.0

    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union_area = box1_area + box2_area - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


BALL_DIAMETER_M = 0.2  # футзальный мяч №4: окружность 62–64 см
BALL_HIT_TOL_PX = 4.0  # клик по мячу 5 px неточен на пару пикселей
BALL_SIZE_BINS = (("<6px", 0.0, 6.0), ("6-10px", 6.0, 10.0), (">=10px", 10.0, np.inf))


def evaluate_ball(detections: pl.DataFrame, labels: pl.DataFrame, venue, conf_min: float) -> dict:
    """Сравнивает детекции мяча с ручной разметкой (схема ball_labels).

    recall — доля кадров с видимым мячом, где хоть одна детекция накрывает клик;
    false_alarm_rate — доля кадров «мяча нет в кадре», где детектор что-то нашёл;
    precision — доля кадров с детекцией (visible + absent), где самая уверенная детекция
    и есть мяч: дальше по пайплайну идёт именно она. Кадры hidden не учитываются.
    Детекции дальше запаса venue.ball_margin_px за контуром поля отброшены, как в process_ball_trajectory.
    """
    from aifootball.geometry.polygons import points_near_polygon

    balls = detections.filter((pl.col("cls") == "ball") & (pl.col("conf") >= conf_min))
    if not balls.is_empty() and venue.pitch_polygon_px is not None:
        centers = np.column_stack([
            ((balls["x1"] + balls["x2"]) / 2).to_numpy(),
            ((balls["y1"] + balls["y2"]) / 2).to_numpy(),
        ])
        balls = balls.filter(pl.Series(points_near_polygon(centers, venue.pitch_polygon_px, venue.ball_margin_px)))
    by_frame = {
        key[0]: g.sort("conf", descending=True).select("x1", "y1", "x2", "y2").to_numpy()
        for key, g in balls.partition_by("frame_id", as_dict=True).items()
    }

    def covers(box, x, y) -> bool:
        t = BALL_HIT_TOL_PX
        return box[0] - t <= x <= box[2] + t and box[1] - t <= y <= box[3] + t

    visible = labels.filter(pl.col("status") == "visible")
    absent = labels.filter(pl.col("status") == "absent")
    found = np.zeros(len(visible), dtype=bool)
    top_right = top_wrong = 0
    for i, row in enumerate(visible.iter_rows(named=True)):
        boxes = by_frame.get(row["frame_id"])
        if boxes is None:
            continue
        found[i] = any(covers(b, row["x"], row["y"]) for b in boxes)
        if covers(boxes[0], row["x"], row["y"]):
            top_right += 1
        else:
            top_wrong += 1
    false_alarms = sum(frame_id in by_frame for frame_id in absent["frame_id"].to_list())
    top_wrong += false_alarms

    by_size = None  # без гомографии размер мяча в пикселях не посчитать
    if venue.H is not None:
        by_size = {}
        sizes = ball_size_px(visible.select("x", "y").to_numpy(), venue) if len(visible) else np.zeros(0)
        for name, lo, hi in BALL_SIZE_BINS:
            in_bin = (sizes >= lo) & (sizes < hi)
            by_size[name] = {
                "visible": int(in_bin.sum()),
                "found": int(found[in_bin].sum()),
                "recall": _ratio(found[in_bin].sum(), in_bin.sum()),
            }

    return {
        "conf_min": conf_min,
        "visible": len(visible),
        "found": int(found.sum()),
        "recall": _ratio(found.sum(), len(visible)),
        "absent": len(absent),
        "false_alarm_frames": false_alarms,
        "false_alarm_rate": _ratio(false_alarms, len(absent)),
        "hidden": int((labels["status"] == "hidden").sum()),
        "precision": _ratio(top_right, top_right + top_wrong),
        "by_size": by_size,
    }


def ball_size_px(points_px: np.ndarray, venue) -> np.ndarray:
    """Ожидаемый диаметр мяча в пикселях в точках кадра, по гомографии.

    Мяч — шар, перспективой пола он не сплющивается, поэтому масштаб берём
    наибольший по направлениям — как в pixels_per_meter.
    """
    from aifootball.geometry.homography import apply_homography, pixels_per_meter
    from aifootball.geometry.undistort import undistort_points

    pts = np.asarray(points_px, dtype=float).reshape(-1, 2)
    meters = apply_homography(venue.H, undistort_points(pts, venue.calib))
    return BALL_DIAMETER_M * pixels_per_meter(venue.H, meters)


def _ratio(num, den) -> float | None:
    return round(float(num) / float(den), 3) if den else None


PASS_MATCH_TOL_S = 1.0  # приём мяча по журналу и по пайплайну: клавишу жмут с запаздыванием


def truth_from_touches(touches: pl.DataFrame) -> tuple[list[tuple[float, float, str | None]], list[dict]]:
    """Эталон из ручного журнала владения: интервалы (начало, конец, команда | None) и передачи.

    Мяч принадлежит команде от момента, когда его получил её игрок, до следующей отметки —
    полёт паса засчитывается отдающим. Передача — две отметки игроков подряд: своему — точная,
    сопернику — неточная (сюда же попадает отбор). После dead мяч ничей до следующей отметки.
    """
    ev = touches.sort("ts").to_dicts()
    teams = ("A", "B")
    intervals = [(a["ts"], b["ts"], a["event"] if a["event"] in teams else None) for a, b in zip(ev, ev[1:])]
    passes = [{"team": a["event"], "completed": b["event"] == a["event"], "ts_receive": b["ts"]}
              for a, b in zip(ev, ev[1:]) if a["event"] in teams and b["event"] in teams]
    return intervals, passes


def evaluate_possession(ball_state: pl.DataFrame, player_state: pl.DataFrame, touches: pl.DataFrame,
                        tol_s: float = PASS_MATCH_TOL_S) -> dict:
    """Сравнивает владение и передачи пайплайна с ручным журналом на отрезке от первой до последней отметки."""
    from aifootball.perception.ball import ball_owners, compute_possession, pass_events

    intervals, truth_passes = truth_from_touches(touches)
    if not intervals:
        raise ValueError("в журнале меньше двух отметок")
    t0, t1 = intervals[0][0], intervals[-1][1]
    in_span = (pl.col("ts") >= t0) & (pl.col("ts") < t1)
    ball = ball_state.filter(in_span)
    players = player_state.filter(in_span)

    truth_s = {"A": 0.0, "B": 0.0, "dead": 0.0}
    for start, end, team in intervals:
        truth_s[team or "dead"] += end - start
    in_play = truth_s["A"] + truth_s["B"]
    truth_pct = {t: round(truth_s[t] / in_play * 100, 1) if in_play else 0.0 for t in ("A", "B")}
    pipe = compute_possession(ball, players)

    # Покадрово: чья команда у мяча по журналу и по пайплайну (ball_owners, как в compute_possession)
    frames = players.select("frame_id", "ts").unique().sort("frame_id")
    starts = np.array([s for s, _, _ in intervals])
    truth_team = [intervals[max(0, np.searchsorted(starts, ts, side="right") - 1)][2] for ts in frames["ts"]]
    owners = ball_owners(ball, players)
    owner = dict(zip(owners["frame_id"].to_list(), owners["team"].to_list()))
    step = float(np.median(np.diff(frames["ts"].to_numpy()))) if frames.height > 1 else 0.0
    agreement = {g: {"A": 0.0, "B": 0.0, "none": 0.0} for g in ("A", "B", "dead")}
    for fid, g in zip(frames["frame_id"].to_list(), truth_team):
        p = owner.get(fid)
        agreement[g or "dead"][p if p in ("A", "B") else "none"] += step
    agreement = {g: {p: round(v, 1) for p, v in row.items()} for g, row in agreement.items()}

    # Передачи: пара «эталон — пайплайн» с той же командой отдающего и приёмом в пределах tol_s
    pipe_passes = [p for p in pass_events(ball_state, player_state) if t0 <= p["ts_receive"] < t1]
    used, matched = set(), []
    for tp in truth_passes:
        best = None
        for i, pp in enumerate(pipe_passes):
            dt = abs(pp["ts_receive"] - tp["ts_receive"])
            if i not in used and pp["team"] == tp["team"] and dt <= tol_s and (best is None or dt < best[1]):
                best = (i, dt)
        if best is not None:
            used.add(best[0])
            matched.append((tp, pipe_passes[best[0]]))

    def counts(passes):
        return {t: {"total": sum(p["team"] == t for p in passes),
                    "completed": sum(p["team"] == t and p["completed"] for p in passes)} for t in ("A", "B")}

    matched_ids = {id(tp) for tp, _ in matched}
    return {
        "span_s": [round(t0, 2), round(t1, 2)],
        "possession": {"truth_s": {k: round(v, 1) for k, v in truth_s.items()}, "truth_pct": truth_pct,
                       "pipeline_s": pipe["possession_s"], "pipeline_pct": pipe["possession_pct"]},
        "possession_by_time_s": agreement,
        "passes": {
            "truth": counts(truth_passes), "pipeline": counts(pipe_passes),
            "matched": len(matched), "recall": _ratio(len(matched), len(truth_passes)),
            "precision": _ratio(len(matched), len(pipe_passes)),
            "completed_agree": sum(tp["completed"] == pp["completed"] for tp, pp in matched),
            "missed_ts": [round(tp["ts_receive"], 1) for tp in truth_passes if id(tp) not in matched_ids],
            "false_ts": [round(pp["ts_receive"], 1) for i, pp in enumerate(pipe_passes) if i not in used],
        },
    }
