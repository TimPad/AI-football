import json

import numpy as np
import polars as pl
import pytest

from aifootball.understanding.per_second_pilot import (VERSION, cv_hints, follow_keys, per_second_prompt,
                                                       project_per_second, window_seconds)


def test_window_seconds_round_partial_last_second():
    assert window_seconds(11948) == 12 and window_seconds(12000) == 12 and window_seconds(400) == 1


def points(times, xs, ys):
    return np.column_stack([times, xs, ys]).astype(float)


def test_follow_keys_center_on_the_ball_every_half_second_and_stay_inside_frame():
    t = np.arange(0, 12, 1 / 15) + 100.0
    ball = points(t, 1000 + 50 * (t - 100), np.full(len(t), 900.0))
    follow = follow_keys(ball, np.zeros((0, 3)), start_s=100.0, duration_s=11.948, frame_w=2592, frame_h=1944)
    assert follow['size'] == [1296, 972]
    assert [k[0] for k in follow['keys']] == [i / 2 for i in range(24)]
    for time, x, y in follow['keys']:
        assert x % 2 == 0 and y % 2 == 0 and 0 <= x <= 2592 - 1296 and 0 <= y <= 1944 - 972
        assert abs(x + 648 - (1000 + 50 * time)) <= 30 and abs(y + 486 - 900) <= 2


def test_follow_keys_ignore_a_single_spike_and_clamp_at_the_frame_edge():
    t = np.arange(0, 4, 1 / 15)
    xs = np.full(len(t), 200.0)
    xs[30] = 2500.0  # одна ложная детекция
    follow = follow_keys(points(t, xs, np.full(len(t), 100.0)), np.zeros((0, 3)), start_s=0.0, duration_s=4.0,
                         frame_w=2592, frame_h=1944)
    assert all(x == 0 and y == 0 for _, x, y in follow['keys'])


def test_follow_keys_use_players_without_ball_and_frame_centre_without_anything():
    t = np.arange(0, 2, 1 / 15)
    players = points(np.repeat(t, 2), np.tile([1500.0, 1700.0], len(t)), np.full(2 * len(t), 1000.0))
    follow = follow_keys(np.zeros((0, 3)), players, start_s=0.0, duration_s=2.0, frame_w=2592, frame_h=1944)
    assert all(abs(x + 648 - 1600) <= 2 and abs(y + 486 - 1000) <= 2 for _, x, y in follow['keys'])
    empty = follow_keys(np.zeros((0, 3)), np.zeros((0, 3)), start_s=0.0, duration_s=2.0, frame_w=2592, frame_h=1944)
    assert all((x, y) == (648, 486) for _, x, y in empty['keys'])


def test_prompt_asks_for_one_answer_per_second_and_adds_cv_hints_only_when_given():
    plain = json.loads(per_second_prompt(11948))
    assert plain['schema_version'] == VERSION and plain['seconds'] == 12 and 'cv_hints' not in plain
    assert 'json' in plain['instruction'].lower() and '12' in plain['response_format']['ball_in_play']
    hints = [{'t': 0, 'players_speed_p80_m_s': 2.1, 'ball_seen_share': 0.5, 'ball_xy_m': [3.0, 4.0],
              'ball_outside_pitch': False}]
    with_cv = json.loads(per_second_prompt(11948, hints=hints))
    assert with_cv['cv_hints'] == hints and len(with_cv['instruction']) > len(plain['instruction'])
    # Варианты с подсказками и без отличаются только подсказками и их описанием.
    assert {k: v for k, v in with_cv.items() if k not in ('cv_hints', 'instruction')} == \
           {k: v for k, v in plain.items() if k != 'instruction'}
    assert with_cv['instruction'].startswith(plain['instruction'])


def answer(states, shots=None, **extra):
    doc = {'schema_version': VERSION, 'ball_in_play': states, **extra}
    if shots is not None:
        doc['shots'] = shots
    return doc


def test_projection_builds_window_local_seconds_and_shot_events():
    states = ['playing'] * 10 + ['stoppage', 'unknown']
    projected, repairs = project_per_second(answer(states, [{'ms': 3500, 'outcome': 'saved'}]), 11948)
    assert repairs == []
    assert projected['states'][0] == {'kind': 'playing', 'start_ms': 0, 'end_ms': 1000}
    assert projected['states'][-1] == {'kind': 'unknown', 'start_ms': 11000, 'end_ms': 11948}
    assert projected['events'] == [{'kind': 'shot_candidate', 'start_ms': 3500, 'end_ms': 3500, 'outcome': 'saved'}]


def test_projection_fills_only_missing_metadata_and_empty_shot_list_with_audit():
    doc = {'ball_in_play': ['playing'] * 12}
    projected, repairs = project_per_second(doc, 11948)
    assert repairs == ['request_metadata:schema_version', 'missing_empty_list:shots']
    assert projected['events'] == [] and 'schema_version' not in doc


@pytest.mark.parametrize('doc', [
    answer(['playing'] * 11, []),
    answer(['playing'] * 11 + ['dead'], []),
    answer(['playing'] * 12, [{'ms': 12000, 'outcome': 'saved'}]),
    answer(['playing'] * 12, [{'ms': 100, 'outcome': 'offside'}]),
    answer(['playing'] * 12, [], notes='лишнее поле'),
    {**answer(['playing'] * 12, []), 'schema_version': 'joint-pilot-v1'},
    [],
])
def test_projection_rejects_answers_that_cannot_be_scored_without_guessing(doc):
    with pytest.raises(ValueError):
        project_per_second(doc, 11948)


def test_cv_hints_report_speed_ball_share_position_and_outside_flag():
    state = pl.DataFrame({'ts': [t / 10 for t in range(20)], 'role': ['player'] * 20,
                          'speed': [1.0] * 10 + [4.0] * 10})
    frames = pl.DataFrame({'ts': [t / 10 for t in range(20)]})
    ball = pl.DataFrame({'ts': [0.1, 0.2, 1.1], 'x_m': [10.0, 10.2, 40.0], 'y_m': [5.0, 5.0, 8.0],
                         'interpolated': [False, False, False]})
    hints = cv_hints(state, ball, frames, start_ms=0, seconds=3, length_m=37.32, width_m=17.68)
    assert [h['t'] for h in hints] == [0, 1, 2]
    assert hints[0]['ball_seen_share'] == 0.2 and hints[0]['ball_xy_m'] == [10.1, 5.0]
    assert hints[0]['ball_outside_pitch'] is False and hints[1]['ball_outside_pitch'] is True
    assert hints[2]['ball_xy_m'] is None and hints[2]['ball_outside_pitch'] is None
    assert hints[2]['ball_seen_share'] is None
    assert hints[0]['players_speed_p80_m_s'] == 4.0
