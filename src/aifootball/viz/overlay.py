"""Боксы треков поверх исходного кадра."""

import cv2
import numpy as np

from aifootball.viz.topdown import TEAM_BGR, UNKNOWN_BGR

POLYGON_BGR = (0, 220, 255)
OFF_PITCH_BGR = (110, 110, 110)


def draw_tracks(frame: np.ndarray, rows, polygon: np.ndarray | None = None) -> np.ndarray:
    """rows — словари из tracks.parquet. Кто вне поля — тонкой серой рамкой."""
    img = frame.copy()
    if polygon is not None:
        cv2.polylines(img, [np.asarray(polygon, np.int32).reshape(-1, 1, 2)], True, POLYGON_BGR, 1)
    for row in rows:
        p1 = (int(row["x1"]), int(row["y1"]))
        p2 = (int(row["x2"]), int(row["y2"]))
        if row["in_pitch"]:
            color, thickness = TEAM_BGR.get(row["team"], UNKNOWN_BGR), 2
        else:
            color, thickness = OFF_PITCH_BGR, 1
        cv2.rectangle(img, p1, p2, color, thickness)
        cv2.putText(
            img, str(row["track_id"]), (p1[0], max(p1[1] - 4, 10)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA,
        )
    return img
