import base64

import cv2
import numpy as np
import pytest

from aifootball.perception.frames import iter_frames
from aifootball.report.frames import STILL_W, THUMB_H, grab_images
from conftest import frame_level, write_vfr_video


def _decode(uri):
    raw = base64.b64decode(uri.split(',', 1)[1])
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def test_grab_thumb_and_still(tiny_video):
    images = grab_images(
        tiny_video,
        {
            'thumb:1': {'kind': 'thumb', 'frame_id': 10, 'ts': 0.4, 'box': [100, 50, 140, 150]},
            'moment:all:0': {'kind': 'still', 'frame_id': 20, 'ts': 0.8, 'box': [100, 50, 140, 150]},
            'moment:all:1': {'kind': 'still', 'frame_id': 30, 'ts': 1.2, 'box': None},
        },
    )
    assert set(images) == {'thumb:1', 'moment:all:0', 'moment:all:1'}
    assert all(uri.startswith('data:image/jpeg;base64,') for uri in images.values())
    assert _decode(images['thumb:1']).shape[0] == THUMB_H
    assert _decode(images['moment:all:1']).shape[1] == STILL_W


def test_missing_frame_is_skipped(tiny_video):
    request = {'kind': 'thumb', 'frame_id': 999, 'ts': 39.96, 'box': [0, 0, 10, 10]}
    assert grab_images(tiny_video, {'thumb:1': request}) == {}


def test_images_are_taken_by_frame_time_on_variable_frame_rate(tmp_path):
    """Номер кадра на плавающем шаге не годится для перемотки: OpenCV считает его по fps и промахивается."""
    video = write_vfr_video(tmp_path / 'vfr.mp4')
    frames = {fid: (ts, frame) for fid, ts, frame in iter_frames(video, 100)}
    picked = (40, 150, 151, 260)
    requests = {
        f'moment:all:{fid}': {'kind': 'still', 'frame_id': fid, 'ts': frames[fid][0], 'box': None} for fid in picked
    }
    images = grab_images(video, requests)
    for fid in picked:
        assert frame_level(_decode(images[f'moment:all:{fid}'])) == pytest.approx(frame_level(frames[fid][1]), abs=2)
