"""Кадры фрагмента для признаков внешности: крупные, целые, без чужих рамок поверх, не у края кадра."""

import numpy as np
import polars as pl

from aifootball import schemas
from aifootball.perception.person_crops import CANDIDATES, KEEP, extract_crops, pick_frames
from conftest import write_video


def row(frame_id, track_id, box, ts=None, role='player', in_pitch=True):
    x1, y1, x2, y2 = box
    return {
        'frame_id': frame_id,
        'ts': frame_id * 0.1 if ts is None else ts,
        'cls': 'person',
        'x1': x1,
        'y1': y1,
        'x2': x2,
        'y2': y2,
        'conf': 0.9,
        'torso_l': None,
        'torso_a': None,
        'torso_b': None,
        'track_id': track_id,
        'foot_x': (x1 + x2) / 2,
        'foot_y': y2,
        'in_pitch': in_pitch,
        'role': role,
        'team': 'A',
    }


def tracks(rows):
    return pl.DataFrame(rows).cast(schemas.TRACKS)


def test_frames_skip_small_edge_covered_and_off_pitch_boxes():
    rows = [row(k, 1, (100, 50, 140, 150)) for k in range(60)]  # 6 с, рамка 100 px
    rows.append(row(5, 2, (102, 52, 142, 152)))  # кадр 5: чужая рамка поверх первой
    rows += [row(k, 3, (200, 100, 220, 140)) for k in range(30)]  # 40 px — мелко
    rows += [row(k, 4, (2, 50, 40, 150)) for k in range(30)]  # у края кадра
    rows += [row(k, 5, (250, 50, 290, 150), role='referee') for k in range(30)]
    rows += [row(k, 6, (300, 50, 340, 150), in_pitch=False) for k in range(30)]
    picks = pick_frames(tracks(rows), (400, 300))
    assert set(picks) == {1}
    ts = sorted(p['ts'] for p in picks[1])
    assert len(ts) <= CANDIDATES and all(b - a >= 1.0 - 1e-9 for a, b in zip(ts, ts[1:]))
    assert all(p['frame_id'] != 5 for p in picks[1])


def test_frames_respect_registration_and_broadcast_graphics():
    rows = [row(k, 1, (100, 50, 140, 150)) for k in range(60)]
    picks = pick_frames(tracks(rows), (400, 300), usable_frames={10, 30})
    assert sorted(p['frame_id'] for p in picks[1]) == [10, 30]
    # центр рамки (120, 100) внутри графики трансляции (доли кадра) — кадров нет
    assert pick_frames(tracks(rows), (400, 300), overlay=((0.2, 0.2, 0.5, 0.5),)) == {}


def test_crops_are_cut_from_the_video_by_timestamp(tmp_path):
    video = write_video(tmp_path / 'clip.mp4', n_frames=40, fps=10, size=(400, 300))
    picks = {1: [{'ts': t, 'frame_id': int(t * 10), 'box': [100, 50, 140, 150]} for t in (0.5, 1.5, 2.5)]}
    crops = extract_crops(video, picks)
    assert len(crops[1]) == min(KEEP, 3)
    assert all(c.shape == (100, 40, 3) for c in crops[1])
    assert isinstance(crops[1][0], np.ndarray)


def test_package_gets_a_colour_appearance_per_fragment(tmp_path, venue):
    from aifootball.analytics.exchange import appearance_ok
    from aifootball.processor.job import appearance

    video = write_video(tmp_path / 'clip.mp4', n_frames=40, fps=10, size=(400, 300))
    rows = [row(k, 1, (100, 50, 140, 150)) for k in range(30)] + [row(k, 2, (200, 100, 220, 130)) for k in range(30)]
    looks = appearance(video, tracks(rows), venue, tmp_path, {1, 2}, (400, 300))
    # У второго рамка 30 px — годных кадров нет, признака тоже.
    assert set(looks) == {1} and appearance_ok(looks[1])
