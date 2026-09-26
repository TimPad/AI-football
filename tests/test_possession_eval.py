import polars as pl
import pytest

from aifootball import schemas
from aifootball.analytics.validation import evaluate_possession, truth_from_touches
from aifootball.tools.label_touches import Touches

FPS = 10
PLAYERS = {1: ("A", 10.0), 2: ("A", 20.0), 3: ("B", 30.0)}  # track_id: (команда, x_m); y_m = 5


def _ball_x(frame: int) -> float:
    """A1 ведёт 0–1.9 с, пас A2 (полёт 2.0–2.4), A2 ведёт 2.5–4.9, пас сопернику, B ведёт 5.5–7.9, дальше мяч далеко."""
    if frame < 20:
        return 10.0
    if frame < 25:
        return 15.0
    if frame < 50:
        return 20.0
    if frame < 55:
        return 25.0
    if frame < 80:
        return 30.0
    return 50.0


def _match():
    frames = range(100)
    ball = pl.DataFrame({"frame_id": list(frames), "ts": [f / FPS for f in frames],
                         "x_m": [_ball_x(f) for f in frames], "y_m": [5.0] * 100,
                         "speed": [0.0] * 100, "interpolated": [False] * 100})
    rows = [{"frame_id": f, "ts": f / FPS, "track_id": tid, "role": "player", "team": team, "x_m": x, "y_m": 5.0,
             "vx": 0.0, "vy": 0.0, "speed": 0.0, "interpolated": False}
            for f in frames for tid, (team, x) in PLAYERS.items()]
    players = pl.DataFrame(rows, schema=schemas.STATE)
    return ball, players


def _touches(events):
    return pl.DataFrame({"frame_id": [int(t * FPS) for t, _ in events], "ts": [t for t, _ in events],
                         "event": [e for _, e in events]}, schema=schemas.TOUCHES)


def test_truth_from_touches_passes_and_dead_ball():
    intervals, passes = truth_from_touches(_touches([(0.0, "A"), (2.5, "A"), (5.5, "B"), (8.0, "dead"), (9.0, "B")]))
    assert intervals == [(0.0, 2.5, "A"), (2.5, 5.5, "A"), (5.5, 8.0, "B"), (8.0, 9.0, None)]
    # после dead пас не связывается: B в 9.0 — новое владение, а не передача
    assert passes == [{"team": "A", "completed": True, "ts_receive": 2.5},
                      {"team": "A", "completed": False, "ts_receive": 5.5}]


def test_evaluate_possession_matches_pipeline_on_clean_match():
    ball, players = _match()
    r = evaluate_possession(ball, players, _touches([(0.0, "A"), (2.5, "A"), (5.5, "B"), (8.0, "dead")]))
    assert r["possession"]["truth_s"] == {"A": 5.5, "B": 2.5, "dead": 0.0}
    # полёт мяча эталон отдаёт отдающему, пайплайн — никому
    assert r["possession_by_time_s"]["A"] == pytest.approx({"A": 4.5, "B": 0.0, "none": 1.0})
    assert r["possession_by_time_s"]["B"] == pytest.approx({"A": 0.0, "B": 2.5, "none": 0.0})
    p = r["passes"]
    assert p["truth"] == p["pipeline"] == {"A": {"total": 2, "completed": 1}, "B": {"total": 0, "completed": 0}}
    assert (p["matched"], p["recall"], p["precision"], p["completed_agree"]) == (2, 1.0, 1.0, 2)
    assert p["missed_ts"] == [] and p["false_ts"] == []


def test_evaluate_possession_reports_late_and_missing_passes():
    ball, players = _match()
    # приём паса отмечен на 1.5 с позже допуска, и отмечен пас, которого пайплайн не видел
    r = evaluate_possession(ball, players, _touches([(0.0, "A"), (4.1, "A"), (5.5, "B"), (7.0, "B"), (8.0, "dead")]))
    p = r["passes"]
    assert p["matched"] == 1
    assert p["missed_ts"] == [4.1, 7.0]
    assert p["false_ts"] == [2.5]


def test_touches_journal_saves_and_undoes(tmp_path):
    path = tmp_path / "touches.parquet"
    j = Touches(path, fps=FPS)
    j.set(10, "A")
    j.set(30, "B")
    j.set(30, "dead")  # на кадре одна отметка — последняя
    assert Touches(path, fps=FPS).events == {10: "A", 30: "dead"}
    assert j.pop_before(25) == 10
    assert j.pop_before(5) is None
    df = schemas.read(path, "touches")
    assert df.to_dicts() == [{"frame_id": 30, "ts": 3.0, "event": "dead"}]
