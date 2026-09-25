"""Модуль расчета метрик качества (Фаза 2): Precision, Recall, IDF1, MOTA и ошибка проекции.

Все метрики рассчитываются с разбивкой по ближней и дальней половине поля.
"""

import math
import numpy as np
import polars as pl


def evaluate_detections(
    pred_df: pl.DataFrame,
    gt_df: pl.DataFrame,
    iou_threshold: float = 0.5,
) -> dict:
    """Вычисляет Precision, Recall и F1-score детекций.

    Отдельно рассчитывается для ближней и дальней половины поля (по y1).
    """
    if gt_df.is_empty():
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "near_f1": 1.0, "far_f1": 1.0}

    # Делим детекции на ближнюю и дальнюю половину по медиане y1
    y_mid = float(gt_df["y1"].median()) if len(gt_df) else 0.0

    overall = _eval_box_matches(pred_df, gt_df, iou_threshold)

    gt_near = gt_df.filter(pl.col("y1") >= y_mid)
    gt_far = gt_df.filter(pl.col("y1") < y_mid)
    pred_near = pred_df.filter(pl.col("y1") >= y_mid) if not pred_df.is_empty() else pred_df
    pred_far = pred_df.filter(pl.col("y1") < y_mid) if not pred_df.is_empty() else pred_df

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
    width_m: float,
) -> dict:
    """Вычисляет ошибку проекции в метрах (MAE и RMSE).

    Отдельно для ближней (y_m >= width_m / 2) и дальней (y_m < width_m / 2) половины поля.
    """
    if gt_state.is_empty() or pred_state.is_empty():
        return {"mae_m": 0.0, "rmse_m": 0.0, "near_half_mae_m": 0.0, "far_half_mae_m": 0.0}

    joined = gt_state.join(pred_state, on=["frame_id", "track_id"], suffix="_pred")
    if joined.is_empty():
        return {"mae_m": 0.0, "rmse_m": 0.0, "near_half_mae_m": 0.0, "far_half_mae_m": 0.0}

    dx = joined["x_m"].to_numpy() - joined["x_m_pred"].to_numpy()
    dy = joined["y_m"].to_numpy() - joined["y_m_pred"].to_numpy()
    dist = np.hypot(dx, dy)

    half_y = width_m / 2.0
    near_mask = joined["y_m"].to_numpy() >= half_y
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
