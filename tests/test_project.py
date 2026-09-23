import polars as pl
import pytest

from aifootball import schemas
from aifootball.state.project import project_tracks


def _track_rows(n=10):
    rows = []
    for f in range(n):
        base = {
            "frame_id": f, "ts": f / 10, "cls": "person",
            "x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 0.0, "conf": 0.9,
            "torso_l": 0.0, "torso_a": 0.0, "torso_b": 0.0,
            "role": "player", "team": "A",
        }
        rows.append({**base, "track_id": 1, "foot_x": 100.0 + 10 * f, "foot_y": 50.0, "in_pitch": True})
        rows.append({**base, "track_id": 2, "foot_x": 300.0, "foot_y": 900.0, "in_pitch": False})
    return pl.DataFrame(rows, schema=schemas.TRACKS)


def test_projects_pixels_to_meters(venue):
    state = project_tracks(_track_rows(), venue)  # 10 px = 1 м

    assert state["track_id"].unique().to_list() == [1]  # трек вне поля отброшен
    assert state["x_m"].to_list() == pytest.approx([10.0 + f for f in range(10)], abs=1e-4)
    assert state["y_m"].to_list() == pytest.approx([5.0] * 10, abs=1e-4)
    assert state["speed"].to_list() == pytest.approx([10.0] * 10, abs=1e-3)  # 1 м за 0.1 с


def test_nothing_on_pitch_gives_empty_state(venue):
    tracks = _track_rows().filter(pl.col("track_id") == 2)
    assert project_tracks(tracks, venue).is_empty()
