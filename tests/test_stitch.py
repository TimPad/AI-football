import polars as pl
import pytest

from aifootball import schemas
from aifootball.perception.stitch import stitch_tracks


def _track(track_id, start_ts, duration=2.0, a=100.0, b=100.0, foot_x=100.0, foot_y=100.0):
    n = int(duration * 10)
    rows = []
    for i in range(n):
        ts = start_ts + i * 0.1
        f = int(ts * 10)
        rows.append({
            "frame_id": f,
            "ts": ts,
            "cls": "person",
            "x1": foot_x - 10.0,
            "y1": foot_y - 30.0,
            "x2": foot_x + 10.0,
            "y2": foot_y,
            "conf": 0.9,
            "torso_l": 120.0,
            "torso_a": a,
            "torso_b": b,
            "track_id": track_id,
            "foot_x": foot_x + i * 0.5,
            "foot_y": foot_y,
            "in_pitch": True,
            "role": "player",
            "team": "A",
        })
    return rows


def test_stitches_matching_tracks():
    # Трек 1 (ts=0..2s, x=100..110) и Трек 2 (ts=3..5s, x=112..122) того же цвета
    t1 = _track(1, start_ts=0.0, duration=2.0, a=100.0, b=100.0, foot_x=100.0)
    t2 = _track(2, start_ts=3.0, duration=2.0, a=102.0, b=99.0, foot_x=112.0)
    df = pl.DataFrame(t1 + t2, schema=schemas.TRACKS)

    stitched = stitch_tracks(df, max_gap_s=2.0, max_color_dist=10.0)

    # Должен остаться один единый track_id (1)
    assert stitched["track_id"].n_unique() == 1
    assert stitched["track_id"].unique().to_list() == [1]


def test_does_not_stitch_overlapping_tracks():
    # Треки пересекаются во времени (t1: 0..2s, t2: 1..3s)
    t1 = _track(1, start_ts=0.0, duration=2.0, a=100.0, b=100.0)
    t2 = _track(2, start_ts=1.0, duration=2.0, a=100.0, b=100.0)
    df = pl.DataFrame(t1 + t2, schema=schemas.TRACKS)

    stitched = stitch_tracks(df, max_gap_s=2.0)

    assert stitched["track_id"].n_unique() == 2


def test_does_not_stitch_different_colors():
    # Разный цвет формы (a=100 vs a=180)
    t1 = _track(1, start_ts=0.0, duration=2.0, a=100.0, b=100.0)
    t2 = _track(2, start_ts=3.0, duration=2.0, a=180.0, b=100.0)
    df = pl.DataFrame(t1 + t2, schema=schemas.TRACKS)

    stitched = stitch_tracks(df, max_gap_s=2.0, max_color_dist=15.0)

    assert stitched["track_id"].n_unique() == 2


def test_does_not_stitch_far_positions():
    # Перепрыгнул через полполя (x=100 -> x=800)
    t1 = _track(1, start_ts=0.0, duration=2.0, foot_x=100.0)
    t2 = _track(2, start_ts=3.0, duration=2.0, foot_x=800.0)
    df = pl.DataFrame(t1 + t2, schema=schemas.TRACKS)

    stitched = stitch_tracks(df, max_gap_s=2.0, max_spatial_dist_px=100.0)

    assert stitched["track_id"].n_unique() == 2
