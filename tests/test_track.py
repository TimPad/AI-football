import polars as pl

from aifootball import schemas
from aifootball.perception.track import track_people


def _det(frame_id, x, y, conf=0.9, cls="person"):
    return {
        "frame_id": frame_id, "ts": frame_id / 10, "cls": cls,
        "x1": x, "y1": y, "x2": x + 20, "y2": y + 50, "conf": conf,
        "torso_l": 100.0, "torso_a": 150.0, "torso_b": 130.0,
    }


def _two_runners(n_frames=15, skip_second_at=None):
    rows = []
    for f in range(n_frames):
        rows.append(_det(f, 20 + 3 * f, 20))  # внутри поля 0..400 x 0..200
        if f != skip_second_at:
            rows.append(_det(f, 300 + 3 * f, 250))  # ноги на y=300 — за полем
    return pl.DataFrame(rows, schema=schemas.DETECTIONS)


def test_two_objects_get_two_stable_ids(venue):
    tracks = track_people(_two_runners(), venue)

    ids_per_frame = tracks.group_by("frame_id").agg(pl.col("track_id").n_unique())
    assert tracks["track_id"].n_unique() == 2
    # первый кадр трек ещё не подтверждён, дальше — оба объекта в каждом кадре
    assert ids_per_frame.filter(pl.col("frame_id") > 0)["track_id"].to_list() == [2] * 14


def test_id_survives_missed_frame(venue):
    tracks = track_people(_two_runners(skip_second_at=7), venue)

    assert tracks["track_id"].n_unique() == 2


def test_foot_point_and_pitch_flag(venue):
    tracks = track_people(_two_runners(), venue)
    row = tracks.filter(pl.col("frame_id") == 5).sort("x1")

    assert row["foot_x"].to_list() == [45.0, 325.0]  # центр нижней грани
    assert row["foot_y"].to_list() == [70.0, 300.0]
    assert row["in_pitch"].to_list() == [True, False]
    assert set(tracks["role"]) == {"unknown"}


def test_ball_rows_are_not_tracked(venue):
    rows = [_det(f, 20 + 3 * f, 20) for f in range(5)] + [_det(2, 100, 100, cls="ball")]
    tracks = track_people(pl.DataFrame(rows, schema=schemas.DETECTIONS), venue)

    assert set(tracks["cls"]) == {"person"}


def test_matches_tracks_schema(venue):
    tracks = track_people(_two_runners(), venue)
    assert set(tracks.columns) == set(schemas.TRACKS)
