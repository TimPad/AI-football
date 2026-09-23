import cv2
import polars as pl

from aifootball import schemas
from aifootball.viz.debug_video import render_debug_video


def test_debug_video_written(tiny_video, venue, tmp_path):
    tracks = pl.DataFrame([{
        "frame_id": 0, "ts": 0.0, "cls": "person", "x1": 10.0, "y1": 10.0, "x2": 40.0, "y2": 80.0,
        "conf": 0.9, "torso_l": 0.0, "torso_a": 0.0, "torso_b": 0.0, "track_id": 1,
        "foot_x": 25.0, "foot_y": 80.0, "in_pitch": True, "role": "player", "team": "A",
    }], schema=schemas.TRACKS)
    state = pl.DataFrame([{
        "frame_id": 0, "ts": 0.0, "track_id": 1, "role": "player", "team": "A",
        "x_m": 2.5, "y_m": 8.0, "vx": 0.0, "vy": 0.0, "speed": 0.0, "interpolated": False,
    }], schema=schemas.STATE)
    out = tmp_path / "debug.mp4"

    written = render_debug_video(tiny_video, tracks, state, venue, out, max_seconds=1.0)

    cap = cv2.VideoCapture(str(out))
    assert written == 11  # 0.0 .. 1.0 с при 10 fps
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 11
    cap.release()
