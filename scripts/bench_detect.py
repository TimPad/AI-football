"""Замер скорости детекции игроков на реальном видео.

Отвечает на один вопрос: сколько времени займёт обработка матча на этой машине.
Гоняет несколько размеров YOLO11 на разных входных разрешениях и считает,
во что это выливается для матча целиком.

Запуск:
    .venv/bin/python scripts/bench_detect.py data/raw/kostroma_futsal_*.mp4
"""

import argparse
import sys
import time
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO

# Матч в футзале: два тайма по 20 минут чистого времени, запись обычно 45-70 минут.
# Берём 45 как нижнюю границу для оценки.
MATCH_MINUTES = 45

# Пайплайну не нужны все 25 fps: игрок бежит ~5 м/с, на 10 fps это 0.5 м между
# кадрами — ByteTrack такое сшивает без проблем. Прореживание даёт ускорение в 2.5x.
TARGET_FPS = 10

MODELS = ["models/yolo11n.pt", "models/yolo11s.pt", "models/yolo11m.pt"]
IMAGE_SIZES = [960, 1280]
WARMUP_FRAMES = 5
BENCH_FRAMES = 40

PERSON_CLASS = 0  # класс 'person' в COCO


def pick_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def read_frames(video_path: Path, count: int, stride: int = 25) -> list:
    """Берём кадры с шагом, чтобы попасть на разные игровые моменты, а не на один."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        sys.exit(f"не открылось видео: {video_path}")

    frames = []
    idx = 0
    while len(frames) < count:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            frames.append(frame)
        idx += 1
    cap.release()

    if not frames:
        sys.exit("не удалось прочитать ни одного кадра")
    return frames


def bench(model: YOLO, frames: list, imgsz: int, device: str) -> tuple[float, float]:
    """Возвращает (кадров в секунду, среднее число людей в кадре)."""
    for frame in frames[:WARMUP_FRAMES]:
        model.predict(frame, imgsz=imgsz, device=device, classes=[PERSON_CLASS], verbose=False)

    if device == "mps":
        torch.mps.synchronize()

    detections = 0
    start = time.perf_counter()
    for frame in frames:
        results = model.predict(
            frame, imgsz=imgsz, device=device, classes=[PERSON_CLASS], verbose=False
        )
        detections += len(results[0].boxes)

    if device == "mps":
        torch.mps.synchronize()
    elapsed = time.perf_counter() - start

    return len(frames) / elapsed, detections / len(frames)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    args = parser.parse_args()

    if not args.video.exists():
        sys.exit(f"нет файла: {args.video}")

    device = pick_device()
    print(f"устройство: {device}   torch: {torch.__version__}")
    print(f"видео: {args.video.name}")

    frames = read_frames(args.video, BENCH_FRAMES)
    h, w = frames[0].shape[:2]
    print(f"кадр: {w}x{h}   замер на {len(frames)} кадрах\n")

    header = f"{'модель':<12}{'imgsz':>7}{'fps':>9}{'людей':>8}   {'матч ' + str(MATCH_MINUTES) + ' мин':>14}"
    print(header)
    print("-" * len(header))

    frames_per_match = MATCH_MINUTES * 60 * TARGET_FPS

    for model_name in MODELS:
        model = YOLO(model_name)
        for imgsz in IMAGE_SIZES:
            fps, avg_det = bench(model, frames, imgsz, device)
            minutes = frames_per_match / fps / 60
            print(f"{model_name:<12}{imgsz:>7}{fps:>9.1f}{avg_det:>8.1f}   {minutes:>11.0f} мин")

    print(
        f"\nОценка матча: {MATCH_MINUTES} мин записи, обработка на {TARGET_FPS} fps "
        f"вместо 25 ({frames_per_match} кадров)."
    )
    print("Столбец 'людей' включает зрителей на балконе — их отсечёт фильтр по полю.")


if __name__ == "__main__":
    main()
