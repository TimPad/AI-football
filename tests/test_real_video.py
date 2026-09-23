"""Прогон на настоящем видео: YOLO на MPS, минуты. Запуск: pytest -m slow"""

import shutil
import subprocess
from pathlib import Path

import polars as pl
import pytest

from aifootball import schemas
from aifootball.perception.detect import detect_video
from aifootball.venue import load_venue

REPO = Path(__file__).resolve().parents[1]
FRAGMENT = REPO / "data/raw/kostroma_futsal_x-ITNQMFm0M_115-415.mp4"
MODELS = REPO / "models"
VENUE = REPO / "configs/venues/kostroma"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not FRAGMENT.exists(), reason="нет фрагмента видео в data/raw"),
    pytest.mark.skipif(not (MODELS / "yolo11m.pt").exists(), reason="нет весов в models/"),
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="нет ffmpeg"),
]


def test_detection_on_ten_seconds_of_real_match(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(FRAGMENT), "-t", "10", "-c", "copy", str(clip)], check=True)
    venue = load_venue(VENUE)

    detections = detect_video(clip, venue, MODELS / venue.model)

    per_frame = detections.filter(pl.col("cls") == "person").group_by("frame_id").len()["len"]
    # 10 с при 10 fps; «-c copy» режет по ключевым кадрам, поэтому ±1 кадр
    assert abs(detections["frame_id"].n_unique() - 100) <= 1
    assert 8 <= per_frame.median() <= 60  # игроки плюс зрители на балконе
    assert detections.schema == pl.Schema(schemas.DETECTIONS)
