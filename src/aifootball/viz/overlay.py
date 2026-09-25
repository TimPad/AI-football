"""Боксы треков и следы движения игроков поверх исходного кадра (Supervision)."""

import cv2
import numpy as np
import supervision as sv

POLYGON_BGR = (0, 220, 255)
OFF_PITCH_BGR = (110, 110, 110)

# Цветовая палитра по class_id для Supervision:
# 0: Team A (зеленый)
# 1: Team B (фиолетовый/розовый)
# 2: Goalkeeper (бирюзовый)
# 3: Referee (ярко-желтый)
# 4: Unknown (серый)
TEAM_PALETTE = sv.ColorPalette([
    sv.Color(r=80, g=200, b=80),
    sv.Color(r=230, g=90, b=200),
    sv.Color(r=255, g=220, b=0),
    sv.Color(r=0, g=220, b=255),
    sv.Color(r=160, g=160, b=160),
])


class TrackAnnotator:
    """Визуализатор треков и следов движения игроков на базе Supervision."""

    def __init__(self, trace_length: int = 30):
        self.trace_annotator = sv.TraceAnnotator(
            color=TEAM_PALETTE,
            trace_length=trace_length,
            thickness=2,
            position=sv.Position.BOTTOM_CENTER,
        )
        self.box_annotator = sv.BoxAnnotator(color=TEAM_PALETTE, thickness=2)
        self.label_annotator = sv.LabelAnnotator(
            color=TEAM_PALETTE,
            text_scale=0.45,
            text_padding=4,
        )

    def annotate(self, frame: np.ndarray, rows, polygon: np.ndarray | None = None) -> np.ndarray:
        img = frame.copy()
        if polygon is not None:
            cv2.polylines(img, [np.asarray(polygon, np.int32).reshape(-1, 1, 2)], True, POLYGON_BGR, 1)

        if not rows:
            return img

        on_pitch_rows = [r for r in rows if r["in_pitch"]]
        off_pitch_rows = [r for r in rows if not r["in_pitch"]]

        # Для объектов вне поля рисуем тонкую серую рамку
        for row in off_pitch_rows:
            p1 = (int(row["x1"]), int(row["y1"]))
            p2 = (int(row["x2"]), int(row["y2"]))
            cv2.rectangle(img, p1, p2, OFF_PITCH_BGR, 1)
            cv2.putText(
                img, f"#{row['track_id']}", (p1[0], max(p1[1] - 4, 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, OFF_PITCH_BGR, 1, cv2.LINE_AA
            )

        if not on_pitch_rows:
            return img

        xyxy = np.array([[r["x1"], r["y1"], r["x2"], r["y2"]] for r in on_pitch_rows], dtype=np.float32)
        track_ids = np.array([r["track_id"] for r in on_pitch_rows], dtype=int)

        class_ids = []
        labels = []
        for r in on_pitch_rows:
            tid = r["track_id"]
            role = r.get("role", "player")
            team = r.get("team")

            if role == "goalkeeper":
                class_ids.append(2)
                labels.append(f"#{tid} GK ({team})")
            elif role == "referee":
                class_ids.append(3)
                labels.append(f"#{tid} REF")
            elif team == "A":
                class_ids.append(0)
                labels.append(f"#{tid} A")
            elif team == "B":
                class_ids.append(1)
                labels.append(f"#{tid} B")
            else:
                class_ids.append(4)
                labels.append(f"#{tid}")

        detections = sv.Detections(
            xyxy=xyxy,
            confidence=np.array([r.get("conf", 1.0) for r in on_pitch_rows], dtype=np.float32),
            class_id=np.array(class_ids, dtype=int),
            tracker_id=track_ids,
        )

        img = self.trace_annotator.annotate(scene=img, detections=detections)
        img = self.box_annotator.annotate(scene=img, detections=detections)
        img = self.label_annotator.annotate(scene=img, detections=detections, labels=labels)

        return img


_default_annotator = TrackAnnotator()


def draw_tracks(frame: np.ndarray, rows, polygon: np.ndarray | None = None) -> np.ndarray:
    return _default_annotator.annotate(frame, rows, polygon)
