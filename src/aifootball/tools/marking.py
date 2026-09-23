"""Сохранение разметки установки и проверочная картинка «вид сверху»."""

import json
from pathlib import Path

import cv2
import numpy as np

from aifootball.geometry.homography import fit_homography, leave_one_out_error
from aifootball.geometry.undistort import undistort_points
from aifootball.venue import Calibration
from aifootball.viz.topdown import LINE_BGR, canvas_size, draw_pitch, meters_to_canvas


def save_polygon(venue_root: Path, points_px) -> Path:
    points = np.asarray(points_px, dtype=float).reshape(-1, 2)
    if len(points) < 3:
        raise ValueError(f"у контура поля нужно минимум 3 вершины, дано {len(points)}")
    path = venue_root / "pitch_polygon.json"
    path.write_text(json.dumps({"points_px": points.round(1).tolist()}, indent=2), encoding="utf-8")
    return path


def save_homography(venue_root: Path, points_px, points_m, calib: Calibration | None) -> dict:
    """Считает H по кликнутым точкам и сохраняет. Точки хранятся как кликнуты — в сырых пикселях."""
    px = np.asarray(points_px, dtype=float).reshape(-1, 2)
    m = np.asarray(points_m, dtype=float).reshape(-1, 2)
    undistorted = undistort_points(px, calib)
    H, error = fit_homography(undistorted, m)
    loo = leave_one_out_error(undistorted, m) if len(px) > 4 else None
    data = {
        "H": H.tolist(),
        "points": [{"px": p.tolist(), "m": q.tolist()} for p, q in zip(px, m)],
        "reprojection_error_m": round(error, 3),
        "leave_one_out_error_m": None if loo is None else round(loo, 3),
    }
    (venue_root / "homography.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def topdown_preview(
    frame: np.ndarray, H: np.ndarray, length_m: float, width_m: float, calib: Calibration | None = None
) -> np.ndarray:
    """Кадр, «развёрнутый» гомографией в вид сверху, с линиями поля поверх.

    Если H верна, линии на полу кадра лягут на нарисованные линии поля.
    """
    if calib is not None:
        frame = cv2.undistort(frame, calib.K, calib.dist)
    warp = meters_to_canvas(width_m) @ H
    warped = cv2.warpPerspective(frame, warp, canvas_size(length_m, width_m))
    lines = draw_pitch(length_m, width_m)
    mask = np.all(lines == LINE_BGR, axis=2)
    warped[mask] = LINE_BGR
    return warped
