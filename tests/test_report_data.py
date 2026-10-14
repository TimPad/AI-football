from aifootball import schemas

import numpy as np
import pytest

from aifootball.analytics.report_data import hsr_distance, segments, sustained_max_speed


def _run(speeds, dt=0.1):
    ts = np.arange(len(speeds)) * dt
    speed = np.asarray(speeds, dtype=float)
    x = np.concatenate([[0.0], np.cumsum(speed[1:] * dt)])
    return ts, x, np.zeros_like(x), speed


def test_segments_split_on_gap():
    ts = np.array([0.0, 0.1, 0.2, 3.0, 3.1])
    assert [(s.start, s.stop) for s in segments(ts)] == [(0, 3), (3, 5)]


def test_hsr_counts_only_fast_steps():
    ts, x, y, speed = _run([3.0] * 20 + [6.0] * 20 + [3.0] * 20)
    assert hsr_distance(ts, x, y, speed) == pytest.approx(6.0 * 0.1 * 20, abs=0.01)


def test_sustained_speed_ignores_single_spike_and_cap():
    ts, _, _, speed = _run([3.0] * 20 + [9.5] + [3.0] * 20 + [6.0] * 10 + [10.0] * 10)
    # одиночный пик 9.5 сглаживается, 10.0 — упор в фильтр, отбрасывается
    assert sustained_max_speed(ts, speed, cap=10.0) == pytest.approx(6.0)


def test_sustained_speed_none_when_only_capped():
    ts, _, _, speed = _run([10.0] * 20)
    assert sustained_max_speed(ts, speed, cap=10.0) is None

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from report_fixtures import LENGTH, synthetic_match  # noqa: E402

from aifootball.analytics.report_data import assign_goalkeeper_teams, orient, thirds_share  # noqa: E402


def _swap_halves(state, at):
    """После at секунд команды меняются воротами: x -> LENGTH - x."""
    return state.with_columns(
        x_m=pl.when(pl.col("ts") >= at).then(LENGTH - pl.col("x_m")).otherwise(pl.col("x_m"))
    )


def test_goalkeeper_team_follows_side_in_each_half():
    state, _ = synthetic_match()
    state = _swap_halves(state, 100).with_columns(
        team=pl.when(pl.col("role") == "goalkeeper").then(pl.lit("A")).otherwise(pl.col("team")))
    fixed = assign_goalkeeper_teams(state, [(0.0, 100.0), (100.0, 200.0)], LENGTH)
    gk = fixed.filter(pl.col("track_id") == 9)  # вратарь B: в 1-м тайме слева, во 2-м справа
    assert gk.filter(pl.col("ts") < 100)["team"].unique().to_list() == ["B"]
    assert gk.filter(pl.col("ts") >= 100)["team"].unique().to_list() == ["B"]


def test_orient_puts_own_goal_left_in_both_halves():
    state, _ = synthetic_match(sprint=False)
    state = _swap_halves(state, 100)
    oriented, ok = orient(state, [(0.0, 100.0), (100.0, 200.0)], LENGTH)
    assert ok
    a = oriented.filter((pl.col("team") == "A") & (pl.col("role") == "player"))
    # A защищает правые ворота в 1-м тайме и левые во 2-м; после поворота всегда держится слева (x ≈ 11)
    assert a.filter(pl.col("ts") < 100)["x_m"].median() == pytest.approx(11.0, abs=1.0)
    assert a.filter(pl.col("ts") >= 100)["x_m"].median() == pytest.approx(11.0, abs=1.0)


def test_thirds_share_on_oriented_state():
    state, _ = synthetic_match(sprint=False)
    oriented, _ = orient(state, [(0.0, 200.0)], LENGTH)
    shares = thirds_share(oriented, LENGTH)
    # центр команды — x = 11 ± 1.5 м < 40/3: всё время в своей трети
    assert shares == {"A": [100, 0, 0], "B": [100, 0, 0]}



def test_missing_direction_preserves_goalkeeper_team():
    state, _ = synthetic_match(sprint=False)
    one = state.filter(pl.col('team') == 'A')
    fixed = assign_goalkeeper_teams(one, [(0., 200.)], LENGTH)
    assert fixed['team'].unique().to_list() == ['A']
    oriented, ok = orient(one, [(0., 200.)], LENGTH)
    assert not ok
    assert oriented.equals(one)


def test_orientation_rotates_both_axes():
    state, _ = synthetic_match(sprint=False)
    oriented, _ = orient(state, [(0., 200.)], LENGTH, width_m=20.)
    a = oriented.filter(pl.col('track_id') == 11)
    assert a['y_m'][0] == 16.
from aifootball.analytics.report_data import series, team_overview  # noqa: E402


def test_team_overview_numbers():
    state, _ = synthetic_match(sprint=False)
    oriented, _ = orient(state, [(0.0, 200.0)], LENGTH)
    ov = team_overview(state, oriented, LENGTH, 20.0, cap=10.0, period_s=200.0)
    a = ov["A"]
    # 4 игрока бегут по синусоиде амплитудой 3 м с периодом 20 с: 12 м за период, 0.6 м/с = 36 м/мин
    assert a["m_per_min"] == pytest.approx(36.0, rel=0.05)
    assert a["distance_m"] == pytest.approx(4 * 0.6 * 199.5, rel=0.05)
    assert a["hsr_m"] == 0.0 and a["sprints"] == 0
    assert a["width_m"] == pytest.approx(12.0, abs=0.1)  # игроки на y = 4, 8, 12, 16
    assert a["low_data"] is False
    assert len(a["heatmap_s"]) == 40 and len(a["heatmap_s"][0]) == 20


def test_low_data_flag():
    state, _ = synthetic_match(sprint=False)
    one = state.filter(pl.col("track_id").is_in([11, 1]))  # по одному полевому игроку
    oriented, _ = orient(one, [(0.0, 200.0)], LENGTH)
    assert team_overview(one, oriented, LENGTH, 20.0, cap=10.0, period_s=200.0)["A"]["low_data"] is True


def test_series_by_five_minutes():
    state, _ = synthetic_match(seconds=600, sprint=False)
    s = series(state, [(0.0, 600.0)])
    assert s["start_min"] == [0.0, 5.0]
    assert s["A"][0] == pytest.approx(36.0, rel=0.05) and s["B"][1] == pytest.approx(36.0, rel=0.05)

from aifootball.analytics.report_data import moments, player_labels, players_table, thumb_request  # noqa: E402


def test_player_labels_by_team_and_first_seen():
    state, _ = synthetic_match()
    short = state.filter(~((pl.col("track_id") == 4) & (pl.col("ts") > 30)))  # трек 4 — всего 30 с
    labels = player_labels(short, min_s=60.0)
    assert labels[1] == "Игрок 1" and labels[11] == "Игрок 1"
    assert labels[9] == "Вратарь" and labels[19] == "Вратарь"
    assert 4 not in labels


def test_players_table_rows():
    state, _ = synthetic_match()
    oriented, _ = orient(state, [(0.0, 200.0)], LENGTH)
    rows = players_table(state, oriented, player_labels(state, 60.0), LENGTH, 20.0, cap=10.0)
    a1 = next(r for r in rows if r["track_id"] == 11)
    assert a1["team"] == "A" and a1["label"] == "Игрок 1"
    assert a1["hsr_m"] == pytest.approx(21.0, abs=1.5)  # 7 шагов по 3 м со скоростью 6 м/с
    assert a1["vmax_ms"] == pytest.approx(6.0, abs=0.3)
    assert len(rows) == 10


def test_thumb_request_middle_of_longest_segment():
    _, tracks = synthetic_match()
    req = thumb_request(tracks, 11)
    assert req["kind"] == "thumb" and 190 <= req["frame_id"] <= 210
    assert len(req["box"]) == 4


def test_moments_find_sprint():
    state, tracks = synthetic_match()
    labels = player_labels(state, 60.0)
    found = {m["kind"]: m for m in moments(state, tracks, labels, [(0.0, 200.0)], cap=10.0)}
    assert found["sprint"]["track_id"] == 11
    assert 20.0 <= found["sprint"]["ts"] <= 24.0
    assert found["speed"]["track_id"] == 11
    assert {"sprint", "speed", "minute_A", "minute_B"} <= set(found)

import json  # noqa: E402

from aifootball.analytics.report_data import build_report, team_colors  # noqa: E402


class _Venue:
    length_m, width_m, max_physical_speed = LENGTH, 20.0, 10.0


def test_build_report_structure_and_json():
    state, tracks = synthetic_match()
    data = build_report(state, tracks, _Venue(), [(0.0, 100.0), (100.0, 200.0)],
                        {"A": "Зелёные", "B": "Оранжевые"}, video_s=200.0)
    assert [p["key"] for p in data["periods"]] == ["all", "h1", "h2"]
    assert data["match"]["halves_found"] is True and data["match"]["processed_s"] == 200.0
    p = data["periods"][0]
    assert set(p) >= {"teams", "thirds", "series", "players", "moments"}
    assert "11" in data["thumbs"]
    json.dumps(data)  # всё сериализуется


def test_team_colors_fallback_and_hex():
    _, tracks = synthetic_match()
    colors = team_colors(tracks)
    assert set(colors) == {"A", "B"} and all(c.startswith("#") and len(c) == 7 for c in colors.values())
    same = tracks.with_columns(torso_a=pl.lit(100.0))
    assert team_colors(same) == {"A": "#1fae4b", "B": "#f07a1a"}



def test_thirds_percentages_sum_to_one_hundred():
    rows = []
    for frame, x in enumerate([2., 20., 38.]):
        for track in (1, 2):
            rows.append({'frame_id': frame, 'team': 'A', 'role': 'player', 'x_m': x})
    shares = thirds_share(pl.DataFrame(rows), LENGTH)
    assert sum(shares['A']) == 100


def test_heatmap_cells_are_metres_on_fractional_pitch():
    from aifootball.analytics.report_data import heatmap_seconds
    state, _ = synthetic_match(seconds=3, sprint=False)
    single = state.filter(pl.col('track_id') == 11).with_columns(x_m=pl.lit(36.9), y_m=pl.lit(17.1))
    grid = heatmap_seconds(single, 37.32, 17.68)
    assert grid[36][17] == pytest.approx(2.5)
    assert sum(map(sum, grid)) == pytest.approx(2.5)


def test_build_report_handles_missing_tracks_for_stills():
    state, _ = synthetic_match()
    data = build_report(state, schemas.empty('tracks'), _Venue(), [(0., 200.)], {'A': 'A', 'B': 'B'}, 200.)
    assert data['thumbs'] == {}
    assert all(m['still'] is None for m in data['periods'][0]['moments'])


def test_process_coverage_does_not_count_empty_gap():
    state, tracks = synthetic_match(seconds=200, sprint=False)
    state = state.filter((pl.col('ts') < 50) | (pl.col('ts') >= 150))
    tracks = tracks.filter((pl.col('ts') < 50) | (pl.col('ts') >= 150))
    data = build_report(state, tracks, _Venue(), [(0., 200.)], {'A': 'A', 'B': 'B'}, 200.)
    assert data['match']['processed_s'] == pytest.approx(100.)


def test_unknown_team_player_cannot_win_team_moment():
    state, tracks = synthetic_match()
    state = state.with_columns(team=pl.when(pl.col('track_id') == 11).then(pl.lit(None, dtype=pl.Utf8)).otherwise(pl.col('team')))
    found = moments(state, tracks, player_labels(state), [(0., 200.)], cap=10.)
    assert all(m['team'] in ('A', 'B') for m in found)


def test_keeper_outing_does_not_change_team():
    state, _ = synthetic_match(sprint=False)
    state = state.with_columns(x_m=pl.when((pl.col('track_id') == 9) & (pl.col('ts') == 50.)).then(30.).otherwise(pl.col('x_m')))
    fixed = assign_goalkeeper_teams(state, [(0., 200.)], LENGTH)
    assert fixed.filter(pl.col('track_id') == 9)['team'].unique().to_list() == ['B']


def test_report_flags_implausible_displacement():
    state, tracks = synthetic_match(sprint=False)
    state = state.with_columns(x_m=pl.when((pl.col('track_id') == 11) & (pl.col('ts') == 50.)).then(0.).otherwise(pl.col('x_m')))
    data = build_report(state, tracks, _Venue(), [(0., 200.)], {'A': 'A', 'B': 'B'}, 200.)
    assert data['periods'][0]['input_quality']['suspect_steps'] >= 2


def test_process_coverage_uses_actual_variable_frame_steps():
    from aifootball.analytics.report_data import _coverage_seconds
    import polars as pl
    tracks=pl.DataFrame({'ts':[0.,1/15,3/15,4/15,6/15,7/15]})
    # All neighbouring samples are continuous; don't replace every step with the median.
    assert _coverage_seconds(tracks,[(0.,7/15)])==pytest.approx(7/15)
