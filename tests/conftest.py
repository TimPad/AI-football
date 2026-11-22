import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

from aifootball.venue import load_venue

VENUE_YAML = {
    'venue_id': 'test',
    'pitch': {'length_m': 40.0, 'width_m': 20.0},
    'processing': {
        'target_fps': 10,
        'model': 'yolo11m.pt',
        'imgsz': 1280,
        'conf_person': 0.25,
        'conf_ball': 0.10,
    },
}

# Масштаб «10 пикселей = 1 метр»: удобно считать ожидаемые значения в тестах.
SCALE_H = [[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, 0.0, 1.0]]


def make_venue_dir(root: Path, polygon=None, H=None, processing=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    cfg = {**VENUE_YAML, 'processing': {**VENUE_YAML['processing'], **(processing or {})}}
    (root / 'venue.yaml').write_text(yaml.safe_dump(cfg), encoding='utf-8')
    if polygon is not None:
        (root / 'pitch_polygon.json').write_text(json.dumps({'points_px': polygon}))
    if H is not None:
        (root / 'homography.json').write_text(json.dumps({'H': H, 'points': []}))
    return root


def write_video(path: Path, n_frames: int = 50, fps: float = 25.0, size=(320, 240)) -> Path:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*'mp4v'), fps, size)
    for i in range(n_frames):
        writer.write(np.full((size[1], size[0], 3), (i * 5) % 256, dtype=np.uint8))
    writer.release()
    return path


def write_vfr_video(path: Path, size=(400, 200), trim_s: float = 9.9) -> Path:
    """Видео с плавающим шагом кадров и отброшенными кадрами в начале, как в загрузках трансляций VK.

    300 кадров: первые 150 через 0.4 с, остальные через 0.6 с, плюс дрожание 0–20 мс. Номер кадра / fps
    расходится с меткой кадра на десятки кадров. Обрезка копированием с -ss оставляет в файле кадры от
    предыдущего опорного с отрицательной меткой: контейнер считает их, декодер отбрасывает.
    """
    if shutil.which('ffmpeg') is None:
        pytest.skip('нет ffmpeg')
    width, height = size
    source = path.with_name(path.stem + '-source.mp4')
    timeline = '(if(lt(N,150),N*0.4,60+(N-150)*0.6)+mod(N,3)*0.01)/TB'
    raw = b''.join(np.full((height, width, 3), (i * 7) % 256, np.uint8).tobytes() for i in range(300))
    encode = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{width}x{height}']
    encode += ['-r', '2', '-i', '-', '-vf', f"settb=1/1000,setpts='{timeline}'", '-fps_mode', 'passthrough']
    encode += ['-enc_time_base', '1/1000', '-c:v', 'mpeg4', '-q:v', '4', '-g', '20', '-sc_threshold', '1000000000']
    encode += ['-bf', '2', '-video_track_timescale', '1000', str(source)]
    subprocess.run(encode, input=raw, check=True)
    if not trim_s:
        return source.replace(path)
    subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-ss', str(trim_s), '-i', str(source), '-c', 'copy', str(path)], check=True
    )
    source.unlink()
    return path


def decoded_times(video: Path) -> list[float]:
    """Метки декодированных кадров по ffprobe, с."""
    out = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'frame=best_effort_timestamp_time']
        + ['-of', 'csv=p=0', str(video)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [float(line) for line in out.split()]


@pytest.fixture
def venue(tmp_path):
    """Установка с полем 0..400 x 0..200 px и масштабом 10 px = 1 м."""
    polygon = [[0, 0], [400, 0], [400, 200], [0, 200]]
    return load_venue(make_venue_dir(tmp_path / 'venue', polygon=polygon, H=SCALE_H))


@pytest.fixture
def tiny_video(tmp_path):
    return write_video(tmp_path / 'tiny.mp4')
