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


def _role_rows(track_id, foot_x, foot_y, seconds, team="A", a=60.0):
    """Трек, стоящий в точке (foot_x, foot_y) px seconds секунд при 10 fps (venue: 10 px = 1 м)."""
    return [{
        "frame_id": f, "ts": f / 10, "cls": "person",
        "x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 30.0, "conf": 0.9,
        "torso_l": 120.0, "torso_a": a, "torso_b": 140.0,
        "track_id": track_id, "foot_x": foot_x, "foot_y": foot_y,
        "in_pitch": True, "role": "player", "team": team,
    } for f in range(int(seconds * 10))]


def _roles(res, track_id):
    return res.filter(pl.col("track_id") == track_id).select("role", "team").unique().rows()


def test_assign_roles_goalkeeper_and_referee(venue):
    from aifootball.perception.teams import assign_roles

    rows = (_role_rows(1, 200.0, 100.0, 30)  # центр поля
            + _role_rows(2, 20.0, 100.0, 30)  # у левых ворот: x = 2 м
            + _role_rows(3, 200.0, 2.0, 30, a=150.0))  # у бровки: y = 0.2 м
    res = assign_roles(pl.DataFrame(rows, schema=schemas.TRACKS), venue)

    assert _roles(res, 1) == [("player", "A")]
    assert _roles(res, 2)[0][0] == "goalkeeper"
    assert _roles(res, 3) == [("referee", None)]


def test_short_track_at_goal_is_not_goalkeeper(venue):
    # Атакующий полевой игрок 5 с у чужих ворот — не вратарь
    from aifootball.perception.teams import assign_roles

    res = assign_roles(pl.DataFrame(_role_rows(1, 20.0, 100.0, 5), schema=schemas.TRACKS), venue)

    assert _roles(res, 1) == [("player", "A")]


def test_goalkeeper_belongs_to_team_defending_that_goal(venue):
    # Полевые B держатся слева (x = 10 м), A — справа (x = 30 м): левые ворота защищает B
    from aifootball.perception.teams import assign_roles

    rows = (_role_rows(1, 100.0, 100.0, 30, team="B") + _role_rows(2, 300.0, 100.0, 30, team="A")
            + _role_rows(3, 20.0, 100.0, 30, team="A")  # у левых ворот, цвет формы ошибочно дал A
            + _role_rows(4, 380.0, 100.0, 30, team="B"))  # у правых ворот
    res = assign_roles(pl.DataFrame(rows, schema=schemas.TRACKS), venue)

    assert _roles(res, 3) == [("goalkeeper", "B")]
    assert _roles(res, 4) == [("goalkeeper", "A")]


def test_goalkeeper_time_excludes_long_gaps(venue):
    from aifootball.perception.teams import assign_roles
    rows = _role_rows(1, 20.0, 100.0, 5)
    later = _role_rows(1, 20.0, 100.0, 5)
    for r in later:
        r['ts'] += 30
        r['frame_id'] += 300
    res = assign_roles(pl.DataFrame(rows + later, schema=schemas.TRACKS), venue)
    assert _roles(res, 1) == [('player', 'A')]


def test_goalkeeper_team_not_guessed_when_direction_unknown(venue):
    from aifootball.perception.teams import assign_roles
    rows = _role_rows(1, 380.0, 100.0, 30, team='A')
    res = assign_roles(pl.DataFrame(rows, schema=schemas.TRACKS), venue)
    assert _roles(res, 1) == [('goalkeeper', 'A')]


def test_goalkeeper_role_survives_change_of_ends(venue):
    from aifootball.perception.teams import assign_roles
    rows = []
    for offset, flip in [(0, False), (200, True)]:
        for tid, x, team in [(1, 100., 'B'), (2, 300., 'A'), (3, 20., 'A'), (4, 380., 'B')]:
            part = _role_rows(tid, 400-x if flip else x, 100., 30, team)
            for r in part:
                r['ts'] += offset
                r['frame_id'] += offset * 10
            rows.extend(part)
    res = assign_roles(pl.DataFrame(rows, schema=schemas.TRACKS), venue)
    assert _roles(res, 3) == [('goalkeeper', 'B')]
    assert _roles(res, 4) == [('goalkeeper', 'A')]
