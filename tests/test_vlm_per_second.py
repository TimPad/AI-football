import polars as pl
import pytest

from aifootball.understanding.per_second import (auc, ball_visible_seconds, dead_intervals, fit_threshold, match_shots,
                                                 player_speed_seconds, predicted_seconds, reference_seconds,
                                                 score_seconds, stoppage_interval_recall, wilson)


def touches(*pairs):
    return [{'ts': ts, 'event': event} for ts, event in pairs]


def test_dead_intervals_merge_repeated_marks_and_drop_trailing_dead_without_resume():
    log = touches((1.0, 'A'), (5.0, 'dead'), (6.0, 'dead'), (9.0, 'B'), (12.0, 'A'), (20.0, 'dead'))
    assert dead_intervals(log) == [(5.0, 9.0)]


def test_dead_interval_ends_at_next_player_touch_not_at_pass_or_shot_mark():
    log = touches((1.0, 'A'), (5.0, 'dead'), (7.0, 'pass'), (8.0, 'shot'), (9.0, 'B'))
    assert dead_intervals(log) == [(5.0, 9.0)]


def test_reference_labels_only_pure_seconds_inside_labelled_span():
    log = touches((0.5, 'A'), (5.4, 'dead'), (8.0, 'B'), (12.0, 'A'))
    labels, mixed = reference_seconds(log, start_s=0.0, end_s=100.0)
    assert labels == {1: 'playing', 2: 'playing', 3: 'playing', 4: 'playing', 6: 'stoppage', 7: 'stoppage',
                      8: 'playing', 9: 'playing', 10: 'playing', 11: 'playing'}
    assert mixed == 1


def test_reference_is_clipped_to_requested_span():
    log = touches((0.5, 'A'), (5.4, 'dead'), (8.0, 'B'), (12.0, 'A'))
    labels, _ = reference_seconds(log, start_s=3.2, end_s=10.0)
    assert sorted(labels) == [4, 6, 7, 8, 9]


def test_predicted_second_takes_majority_known_state_and_needs_half_a_second():
    states = [{'kind': 'playing', 'start_ms': 0, 'end_ms': 3400}, {'kind': 'stoppage', 'start_ms': 3400, 'end_ms': 6000},
              {'kind': 'unknown', 'start_ms': 6000, 'end_ms': 7000}, {'kind': 'playing', 'start_ms': 7700, 'end_ms': 8000}]
    assert predicted_seconds(states, range(8)) == {0: 'playing', 1: 'playing', 2: 'playing', 3: 'stoppage',
                                                    4: 'stoppage', 5: 'stoppage', 6: 'unknown', 7: 'unknown'}


def test_break_and_match_boundaries_mean_ball_out_of_play():
    states = [{'kind': 'break', 'start_ms': 0, 'end_ms': 1000}, {'kind': 'pre_match', 'start_ms': 1000, 'end_ms': 2000}]
    assert predicted_seconds(states, [0, 1]) == {0: 'stoppage', 1: 'stoppage'}


def test_score_counts_unknown_as_missing_coverage_not_as_correct():
    reference = {0: 'playing', 1: 'playing', 2: 'stoppage', 3: 'stoppage', 4: 'playing'}
    predicted = {0: 'playing', 1: 'stoppage', 2: 'stoppage', 3: 'unknown', 4: 'playing'}
    score = score_seconds(reference, predicted)
    assert score['labelled'] == 5 and score['covered'] == 4 and score['correct'] == 3
    assert score['coverage'] == 0.8 and score['accuracy'] == 0.6 and score['accuracy_covered'] == 0.75
    # «Всегда игра» на тех же отвеченных секундах 0, 1, 2, 4: верно 0, 1 и 4.
    assert score['always_playing_covered'] == 0.75
    assert score['stoppage_precision'] == 0.5 and score['stoppage_recall'] == 0.5
    assert score['playing_recall'] == pytest.approx(2 / 3)
    assert score['balanced_accuracy'] == pytest.approx((2 / 3 + 0.5) / 2)
    assert score['confusion'] == {'playing': {'playing': 2, 'stoppage': 1, 'unknown': 0},
                                  'stoppage': {'playing': 0, 'stoppage': 1, 'unknown': 1}}


def test_score_without_predicted_stoppages_has_no_precision():
    score = score_seconds({0: 'playing', 1: 'stoppage'}, {0: 'playing', 1: 'playing'})
    assert score['stoppage_precision'] is None and score['stoppage_recall'] == 0.0


def test_score_rejects_missing_predictions():
    with pytest.raises(ValueError):
        score_seconds({0: 'playing', 1: 'stoppage'}, {0: 'playing'})


def test_interval_recall_counts_a_dead_ball_once_if_any_scored_second_is_stoppage():
    intervals = [(2.0, 5.0), (8.0, 10.0), (30.0, 40.0)]
    predicted = {2: 'playing', 3: 'stoppage', 4: 'stoppage', 8: 'unknown', 9: 'playing'}
    assert stoppage_interval_recall(intervals, predicted) == {'intervals': 2, 'found': 1}


def test_wilson_interval_matches_known_values_and_handles_empty_samples():
    assert wilson(0, 0) is None
    low, high = wilson(19, 23)
    assert round(low, 2) == 0.63 and round(high, 2) == 0.93
    assert all(wilson(0, n)[0] == 0.0 and wilson(n, n)[1] == 1.0 for n in range(1, 200))


def test_match_shots_uses_only_shot_like_events_within_tolerance():
    shots = [{'ts': 6.91, 'certainty': 'sure'}, {'ts': 37.39, 'certainty': 'sure'}, {'ts': 20.0, 'certainty': 'maybe'}]
    events = [{'kind': 'shot_candidate', 'start_ms': 36000, 'end_ms': 37000},
              {'kind': 'kick_in', 'start_ms': 6800, 'end_ms': 7000},
              {'kind': 'save_candidate', 'start_ms': 50000, 'end_ms': 51000}]
    assert match_shots(shots, events, tolerance_ms=1500) == {'labelled': 3, 'labelled_sure': 2, 'predicted': 2,
                                                             'matched': 1, 'matched_sure': 1}


def test_auc_and_threshold_treat_low_values_as_stoppage():
    values = {0: 0.5, 1: 0.8, 2: 3.0, 3: 4.0}
    reference = {0: 'stoppage', 1: 'stoppage', 2: 'playing', 3: 'playing'}
    assert auc(values, reference) == 1.0
    assert auc({0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0}, reference) == 0.5
    threshold = fit_threshold(values, reference)
    assert 0.8 < threshold <= 3.0


def test_player_speed_uses_a_centered_three_second_window_of_field_players():
    rows = []
    for i in range(100):
        ts = i * 0.1
        rows.append({'ts': ts, 'role': 'player', 'speed': 1.0 if ts < 5 else 5.0})
        rows.append({'ts': ts, 'role': 'goalkeeper', 'speed': 0.0})
    state = pl.DataFrame(rows)
    speed = player_speed_seconds(state, [0, 2, 4, 5, 8], q=0.5)
    # Окно секунды 4 — [3, 6): двадцать замеров 1 м/с и десять по 5 м/с; секунды 5 — наоборот.
    assert speed == {0: 1.0, 2: 1.0, 4: 1.0, 5: 5.0, 8: 5.0}


def test_ball_visible_share_ignores_interpolated_points():
    ball = pl.DataFrame({'ts': [0.1, 0.2, 0.3, 1.1, 1.2], 'interpolated': [False, False, True, True, True]})
    frames = pl.DataFrame({'ts': [0.1, 0.2, 0.3, 0.4, 1.1, 1.2, 1.3, 1.4]})
    assert ball_visible_seconds(ball, frames, [0, 1, 2]) == {0: 0.5, 1: 0.0, 2: None}
