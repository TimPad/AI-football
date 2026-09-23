"""Схема поля сверху и игроки на ней."""

import cv2
import numpy as np

PX_PER_M = 20
MARGIN_M = 2.0
FLOOR_BGR = (55, 55, 55)
LINE_BGR = (235, 235, 235)
TEAM_BGR = {"A": (80, 200, 80), "B": (200, 90, 230)}
UNKNOWN_BGR = (160, 160, 160)
CENTER_CIRCLE_R_M = 3.0
GOAL_WIDTH_M = 3.0
GOAL_DEPTH_M = 1.0


def canvas_size(length_m: float, width_m: float) -> tuple[int, int]:
    """(ширина, высота) холста в пикселях."""
    return (
        int(round((length_m + 2 * MARGIN_M) * PX_PER_M)),
        int(round((width_m + 2 * MARGIN_M) * PX_PER_M)),
    )


def meters_to_canvas(width_m: float) -> np.ndarray:
    """Матрица 3x3: метры поля -> пиксели холста. Дальняя боковая линия — сверху."""
    return np.array([
        [PX_PER_M, 0.0, MARGIN_M * PX_PER_M],
        [0.0, -PX_PER_M, (MARGIN_M + width_m) * PX_PER_M],
        [0.0, 0.0, 1.0],
    ])


def to_canvas(x_m: float, y_m: float, width_m: float) -> tuple[int, int]:
    u, v, _ = meters_to_canvas(width_m) @ np.array([x_m, y_m, 1.0])
    return int(round(u)), int(round(v))


def draw_pitch(length_m: float, width_m: float) -> np.ndarray:
    w, h = canvas_size(length_m, width_m)
    img = np.full((h, w, 3), FLOOR_BGR, dtype=np.uint8)
    L, W = length_m, width_m
    cv2.rectangle(img, to_canvas(0, W, W), to_canvas(L, 0, W), LINE_BGR, 2)
    cv2.line(img, to_canvas(L / 2, 0, W), to_canvas(L / 2, W, W), LINE_BGR, 2)
    cv2.circle(img, to_canvas(L / 2, W / 2, W), int(CENTER_CIRCLE_R_M * PX_PER_M), LINE_BGR, 2)
    half = GOAL_WIDTH_M / 2
    for goal_x, outward in ((0.0, -GOAL_DEPTH_M), (L, GOAL_DEPTH_M)):
        cv2.rectangle(
            img,
            to_canvas(goal_x, W / 2 + half, W),
            to_canvas(goal_x + outward, W / 2 - half, W),
            LINE_BGR,
            2,
        )
    return img


def draw_players(pitch: np.ndarray, rows, width_m: float) -> np.ndarray:
    """rows — словари с x_m, y_m, team, track_id. Рисует на копии."""
    img = pitch.copy()
    for row in rows:
        center = to_canvas(row["x_m"], row["y_m"], width_m)
        color = TEAM_BGR.get(row["team"], UNKNOWN_BGR)
        cv2.circle(img, center, int(0.45 * PX_PER_M), color, -1)
        cv2.putText(
            img, str(row["track_id"]), (center[0] + 10, center[1] - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, LINE_BGR, 1, cv2.LINE_AA,
        )
    return img
