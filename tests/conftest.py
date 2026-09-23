import json
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

from aifootball.venue import load_venue

VENUE_YAML = {
    "venue_id": "test",
    "pitch": {"length_m": 40.0, "width_m": 20.0},
    "processing": {
        "target_fps": 10,
        "model": "yolo11m.pt",
        "imgsz": 1280,
        "conf_person": 0.25,
        "conf_ball": 0.10,
    },
}

# Масштаб «10 пикселей = 1 метр»: удобно считать ожидаемые значения в тестах.
SCALE_H = [[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, 0.0, 1.0]]


def make_venue_dir(root: Path, polygon=None, H=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "venue.yaml").write_text(yaml.safe_dump(VENUE_YAML), encoding="utf-8")
    if polygon is not None:
        (root / "pitch_polygon.json").write_text(json.dumps({"points_px": polygon}))
    if H is not None:
        (root / "homography.json").write_text(json.dumps({"H": H, "points": []}))
    return root


def write_video(path: Path, n_frames: int = 50, fps: float = 25.0, size=(320, 240)) -> Path:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"mp4v"), fps, size)
    for i in range(n_frames):
        writer.write(np.full((size[1], size[0], 3), (i * 5) % 256, dtype=np.uint8))
    writer.release()
    return path


@pytest.fixture
def venue(tmp_path):
    """Установка с полем 0..400 x 0..200 px и масштабом 10 px = 1 м."""
    polygon = [[0, 0], [400, 0], [400, 200], [0, 200]]
    return load_venue(make_venue_dir(tmp_path / "venue", polygon=polygon, H=SCALE_H))


@pytest.fixture
def tiny_video(tmp_path):
    return write_video(tmp_path / "tiny.mp4")
