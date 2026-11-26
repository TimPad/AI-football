import json
import shutil
import subprocess

import cv2
import numpy as np
import pytest

from aifootball.perception.scoreboard import (
    Overlay,
    board_goals,
    load_overlay,
    plate_changes,
    read_plates,
    scoreboard_from_video,
)

FPS = 2


def digit(value: int, size=(24, 40)) -> np.ndarray:
    """Плашка счёта: тёмная цифра на белом, как у «Мяч ТВ»."""
    w, h = size
    plate = np.full((h, w), 255, np.uint8)
    cv2.putText(plate, str(value), (2, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
    return plate


def timeline(states: list[tuple[float, int | None]], duration: float) -> np.ndarray:
    """Кадры плашки 2 раза в секунду: состояние (с какого времени, цифра); None — плашки не видно."""
    frames = []
    for i in range(int(duration * FPS)):
        t = i / FPS
        value = [v for start, v in states if start <= t][-1]
        frames.append(np.zeros((40, 24), np.uint8) if value is None else digit(value))
    return np.stack(frames)


def test_plate_changes_counts_new_digits_after_they_hold():
    frames = timeline([(0, 0), (10, 1), (30, 2)], 50)
    # Время гола — сразу после последнего кадра со старым счётом.
    assert plate_changes(frames, FPS, []) == [10.0, 30.0]


def test_plate_changes_ignores_short_flicker_hidden_plate_and_replays():
    frames = timeline([(0, 0), (8, 1), (9, 0), (15, None), (18, 0), (25, 1), (40, 1)], 50)
    # Вспышка «1» на секунду не гол; скрытая плашка не состояние; смена у повтора (±2 с не читаются) — до него.
    assert plate_changes(frames, FPS, [[24.0, 27.0]]) == [22.0]


def test_plate_changes_does_not_recount_a_corrected_score():
    frames = timeline([(0, 0), (10, 1), (20, 2), (30, 1), (40, 2)], 60)
    # Оператор снял и вернул гол: состояния «1» и «2» уже были — голов два.
    assert plate_changes(frames, FPS, []) == [10.0, 20.0]


def test_board_goals_orders_scores_and_minutes_within_halves():
    board = board_goals({'left': [100.0, 1500.0], 'right': [700.0]}, [(40.0, 1240.0), (1370.0, 2570.0)])
    assert board['final'] == {'left': 2, 'right': 1}
    assert board['goals'] == [
        {'t_s': 100.0, 'side': 'left', 'period': 1, 'elapsed_s': 60.0},
        {'t_s': 700.0, 'side': 'right', 'period': 1, 'elapsed_s': 660.0},
        {'t_s': 1500.0, 'side': 'left', 'period': 2, 'elapsed_s': 130.0},
    ]


def test_board_goals_outside_halves_go_to_the_nearest_half():
    board = board_goals({'left': [10.0, 1300.0], 'right': []}, [(40.0, 1240.0), (1370.0, 2570.0)])
    # До начала — минута 0 первого тайма; в перерыве — конец первого тайма.
    assert [(g['period'], g['elapsed_s']) for g in board['goals']] == [(1, 0.0), (1, 1200.0)]


def test_load_overlay_scales_boxes_to_the_source(tmp_path):
    path = tmp_path / 'overlay.json'
    path.write_text(
        json.dumps({'name': 'Мяч ТВ', 'frame': [1920, 1080], 'left': [300, 96, 56, 34], 'right': [402, 96, 56, 34]})
    )
    overlay = load_overlay(path)
    assert overlay.name == 'Мяч ТВ' and overlay.digits == 'dark'
    assert overlay.scaled((960, 540)).left == (150, 48, 28, 17)


def write_board_video(path, changes: list[tuple[float, int, int]], duration: float, size=(320, 180), fps=10):
    """Видео с табло в левом верхнем углу: (время, счёт слева, счёт справа)."""
    if shutil.which('ffmpeg') is None:
        pytest.skip('нет ffmpeg')
    w, h = size
    frames = []
    for i in range(int(duration * fps)):
        t = i / fps
        left, right = [(a, b) for start, a, b in changes if start <= t][-1]
        frame = np.full((h, w, 3), 90, np.uint8)
        frame[10:50, 20:44] = digit(left)[:, :, None]
        frame[10:50, 60:84] = digit(right)[:, :, None]
        frames.append(frame.tobytes())
    command = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps)]
    command += ['-i', '-', '-c:v', 'mpeg4', '-q:v', '2', str(path)]
    subprocess.run(command, input=b''.join(frames), check=True)
    return path


def test_scoreboard_from_video_reads_both_plates(tmp_path):
    video = write_board_video(tmp_path / 'board.mp4', [(0, 0, 0), (6, 1, 0), (14, 1, 1), (20, 2, 1)], 30)
    overlay = Overlay(name='test', frame=(320, 180), left=(20, 10, 24, 40), right=(60, 10, 24, 40))
    plates = read_plates(video, overlay, (320, 180))
    assert set(plates) == {'left', 'right'} and plates['left'].shape[1:] == (40, 24)
    # Нечётные размеры и сдвиги плашек читаются как заданы (yuv420 округлял бы их до чётных).
    odd = Overlay(name='odd', frame=(320, 180), left=(21, 11, 23, 39), right=(61, 11, 23, 39))
    assert read_plates(video, odd, (320, 180))['right'].shape[1:] == (39, 23)
    board = scoreboard_from_video(video, overlay, (320, 180), [], [(0.0, 30.0)])
    assert board['final'] == {'left': 2, 'right': 1}
    assert [(g['side'], round(g['t_s'])) for g in board['goals']] == [('left', 6), ('right', 14), ('left', 20)]
    assert board['overlay'] == 'test'
