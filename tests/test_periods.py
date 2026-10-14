import polars as pl
import pytest

from aifootball import schemas
from aifootball.analytics.periods import find_halves, in_period, make_periods, parse_halves


def _crowd(seconds, people_at):
    """tracks: в кадре t (1 fps) на поле people_at(t) человек."""
    rows = []
    for t in range(seconds):
        for k in range(people_at(t)):
            rows.append({"frame_id": t, "ts": float(t), "cls": "person", "x1": 0.0, "y1": 0.0, "x2": 10.0,
                         "y2": 30.0, "conf": 0.9, "torso_l": 0.0, "torso_a": 0.0, "torso_b": 0.0,
                         "track_id": k, "foot_x": 5.0, "foot_y": 30.0, "in_pitch": True,
                         "role": "player", "team": "A"})
    return pl.DataFrame(rows, schema=schemas.TRACKS)


def test_parse_halves():
    assert parse_halves("0:40-21:50, 27:10-46:00", 3000) == [(40.0, 1310.0), (1630.0, 2760.0)]


@pytest.mark.parametrize("text", ["0:00-10:00,9:00-20:00", "0:00-60:00", "5:00-1:00"])
def test_parse_halves_rejects_bad_spans(text):
    with pytest.raises(ValueError):
        parse_halves(text, 1500)


def test_find_halves_splits_at_long_break():
    # Игра 0–300 с, перерыв (1 человек) 300–600 с, игра 600–900 с, пустой хвост 900–1000 с
    tracks = _crowd(1000, lambda t: 8 if t < 300 or 600 <= t < 900 else 1)
    halves = find_halves(tracks)
    assert len(halves) == 2
    (s1, e1), (s2, e2) = halves
    assert s1 == pytest.approx(0, abs=10) and e1 == pytest.approx(300, abs=10)
    assert s2 == pytest.approx(600, abs=10) and e2 == pytest.approx(900, abs=10)


def test_find_halves_ignores_short_stoppage():
    # Пауза 60 с — не перерыв
    tracks = _crowd(600, lambda t: 1 if 200 <= t < 260 else 8)
    halves = find_halves(tracks)
    assert len(halves) == 1
    assert halves[0][0] == pytest.approx(0, abs=10) and halves[0][1] == pytest.approx(599, abs=10)


def test_make_periods_and_filter():
    periods = make_periods([(0.0, 10.0), (20.0, 30.0)])
    assert [p.key for p in periods] == ["all", "h1", "h2"]
    assert periods[0].duration_s == 20.0
    df = pl.DataFrame({"ts": [1.0, 15.0, 25.0]})
    assert in_period(df, periods[0].spans)["ts"].to_list() == [1.0, 25.0]
    assert [p.key for p in make_periods([(0.0, 10.0)])] == ["all"]


@pytest.mark.parametrize('text', ['', '0:60-2:00', '0:00-0:nan', '0:00-0:inf', '0:00-1:00,1:00-2:00,2:00-3:00'])
def test_parse_halves_validates_clocks_and_count(text):
    with pytest.raises(ValueError):
        parse_halves(text, 200)


def test_find_halves_handles_empty_field_gap():
    tracks = _crowd(1000, lambda t: 8 if t < 300 or 600 <= t < 900 else 0)
    assert find_halves(tracks) == [(0.0, 300.0), (600.0, 900.0)]
