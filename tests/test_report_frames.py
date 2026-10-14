import base64

import cv2
import numpy as np

from aifootball.report.frames import STILL_W, THUMB_H, grab_images


def _decode(uri):
    raw = base64.b64decode(uri.split(",", 1)[1])
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def test_grab_thumb_and_still(tiny_video):
    images = grab_images(tiny_video, {
        "thumb:1": {"kind": "thumb", "frame_id": 10, "box": [100, 50, 140, 150]},
        "moment:all:0": {"kind": "still", "frame_id": 20, "box": [100, 50, 140, 150]},
        "moment:all:1": {"kind": "still", "frame_id": 30, "box": None},
    })
    assert set(images) == {"thumb:1", "moment:all:0", "moment:all:1"}
    assert all(uri.startswith("data:image/jpeg;base64,") for uri in images.values())
    assert _decode(images["thumb:1"]).shape[0] == THUMB_H
    assert _decode(images["moment:all:1"]).shape[1] == STILL_W


def test_missing_frame_is_skipped(tiny_video):
    assert grab_images(tiny_video, {"thumb:1": {"kind": "thumb", "frame_id": 999, "box": [0, 0, 10, 10]}}) == {}
