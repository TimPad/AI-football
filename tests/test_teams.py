import polars as pl

from aifootball import schemas
from aifootball.perception.teams import assign_teams


def _track(track_id, a, n, in_pitch=True):
    return [
        {
            "frame_id": f, "ts": f / 10, "cls": "person",
            "x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 30.0, "conf": 0.9,
            "torso_l": 120.0, "torso_a": a + (f % 3), "torso_b": 140.0,
            "track_id": track_id, "foot_x": 5.0, "foot_y": 30.0,
            "in_pitch": in_pitch, "role": "unknown", "team": None,
        }
        for f in range(n)
    ]


def _tracks(*groups):
    return pl.DataFrame([row for group in groups for row in group], schema=schemas.TRACKS)


def _team_of(result, track_id):
    return result.filter(pl.col("track_id") == track_id)["team"].unique().to_list()


def test_splits_red_and_green_into_two_teams():
    tracks = _tracks(
        _track(1, a=200, n=12), _track(2, a=195, n=15), _track(3, a=205, n=11),  # красные
        _track(4, a=60, n=12), _track(5, a=70, n=20),  # зелёные
    )

    result = assign_teams(tracks)

    assert _team_of(result, 4) == _team_of(result, 5) == ["A"]  # зеленее — «A»
    assert _team_of(result, 1) == _team_of(result, 2) == _team_of(result, 3) == ["B"]
    assert set(result["role"]) == {"player"}


def test_short_and_off_pitch_tracks_stay_unknown():
    tracks = _tracks(
        _track(1, a=200, n=12), _track(2, a=60, n=12),
        _track(3, a=200, n=4),  # слишком короткий
        _track(4, a=60, n=30, in_pitch=False),  # зритель на балконе
    )

    result = assign_teams(tracks)

    for track_id in (3, 4):
        rows = result.filter(pl.col("track_id") == track_id)
        assert rows["role"].unique().to_list() == ["unknown"]
        assert rows["team"].unique().to_list() == [None]


def test_not_enough_tracks_leaves_everyone_unknown():
    result = assign_teams(_tracks(_track(1, a=200, n=12)))

    assert result["role"].unique().to_list() == ["unknown"]


def test_keeps_tracks_schema():
    result = assign_teams(_tracks(_track(1, a=200, n=12), _track(2, a=60, n=12)))
    assert result.columns == list(schemas.TRACKS)
