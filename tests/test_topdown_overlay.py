import numpy as np

from aifootball.viz.overlay import draw_tracks
from aifootball.viz.topdown import LINE_BGR, TEAM_BGR, canvas_size, draw_pitch, draw_players, to_canvas


def test_canvas_geometry():
    assert canvas_size(40, 20) == (880, 480)
    assert to_canvas(0, 0, 20) == (40, 440)  # ближний левый угол — внизу слева
    assert to_canvas(40, 20, 20) == (840, 40)  # дальний правый — вверху справа


def test_pitch_lines_drawn():
    img = draw_pitch(40, 20)
    u, v = to_canvas(10, 0, 20)  # середина ближней боковой линии

    assert img.shape == (480, 880, 3)
    assert tuple(int(c) for c in img[v, u]) == LINE_BGR


def test_player_drawn_in_team_color_on_copy():
    pitch = draw_pitch(40, 20)
    img = draw_players(pitch, [{"x_m": 10.0, "y_m": 10.0, "team": "A", "track_id": 3}], 20)
    u, v = to_canvas(10, 10, 20)

    assert tuple(int(c) for c in img[v, u]) == TEAM_BGR["A"]
    assert not np.array_equal(img, pitch)


def test_overlay_does_not_touch_input():
    frame = np.zeros((100, 100, 3), np.uint8)
    row = {"x1": 10, "y1": 10, "x2": 40, "y2": 80, "in_pitch": True, "team": "B", "track_id": 1}

    img = draw_tracks(frame, [row])

    assert frame.sum() == 0
    assert tuple(int(c) for c in img[40, 10]) == TEAM_BGR["B"]  # левая грань бокса
