"""Отрисовка детекций поверх кадра — посмотреть глазами, что модель видит.

Делает две вещи:
  1. Сохраняет размеченные кадры: боксы людей с высотой в пикселях и мяч, если найден.
  2. Считает по длинному участку, как часто вообще находится мяч.

Запуск:
    .venv/bin/python scripts/debug_overlay.py data/raw/kostroma_futsal_*.mp4 -o out/
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

PERSON = 0  # COCO 'person'
BALL = 32  # COCO 'sports ball'

MODEL = "models/yolo11m.pt"
IMGSZ = 1280
CONF_PERSON = 0.25
CONF_BALL = 0.10  # мяч мелкий, уверенность заведомо низкая — смотрим что вообще есть

# Секунды, на которых сохраняем размеченные кадры.
SNAPSHOT_SECONDS = [5, 60, 150, 240]

# Сколько кадров просмотреть для статистики по мячу и с каким шагом.
BALL_SCAN_FRAMES = 150
BALL_SCAN_STRIDE = 10

GREEN = (0, 220, 0)
ORANGE = (0, 165, 255)
RED = (0, 0, 255)


def pick_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def draw(frame: np.ndarray, result) -> tuple[np.ndarray, int, int]:
    """Рисует боксы. Цвет по размеру: зелёный — крупный, оранжевый — мелкий."""
    canvas = frame.copy()
    people = balls = 0

    for box in result.boxes:
        cls = int(box.cls)
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
        conf = float(box.conf)
        height = y2 - y1

        if cls == PERSON:
            # Порог у каждого класса свой: predict вызван с низким порогом ради мяча,
            # поэтому людей отсекаем здесь, иначе в кадр лезет половина балкона.
            if conf < CONF_PERSON:
                continue
            people += 1
            color = GREEN if height >= 70 else ORANGE
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                canvas, f"{height}", (x1, max(y1 - 4, 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA,
            )
        elif cls == BALL:
            balls += 1
            # Мяч мелкий — обводим окружностью пожирнее, иначе не найти на картинке.
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            cv2.circle(canvas, (cx, cy), 22, RED, 3)
            cv2.putText(
                canvas, f"ball {conf:.2f}", (cx - 30, cy - 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, RED, 2, cv2.LINE_AA,
            )

    banner = f"people: {people}   balls: {balls}"
    cv2.putText(canvas, banner, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(canvas, banner, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    return canvas, people, balls


def grab(cap: cv2.VideoCapture, frame_index: int) -> np.ndarray | None:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = cap.read()
    return frame if ok else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("-o", "--out", type=Path, required=True)
    args = parser.parse_args()

    if not args.video.exists():
        sys.exit(f"нет файла: {args.video}")
    args.out.mkdir(parents=True, exist_ok=True)

    device = pick_device()
    model = YOLO(MODEL)

    cap = cv2.VideoCapture(str(args.video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"{MODEL} @ {IMGSZ}, {device}, видео {fps:.0f} fps\n")

    # --- размеченные кадры ---
    for second in SNAPSHOT_SECONDS:
        frame = grab(cap, int(second * fps))
        if frame is None:
            print(f"  t={second}s: кадр не прочитался")
            continue

        result = model.predict(
            frame, imgsz=IMGSZ, device=device, classes=[PERSON, BALL],
            conf=min(CONF_PERSON, CONF_BALL), verbose=False,
        )[0]

        canvas, people, balls = draw(frame, result)
        path = args.out / f"overlay_t{second:03d}.jpg"
        cv2.imwrite(str(path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"  t={second:>3}s  людей: {people:>3}  мячей: {balls}  -> {path.name}")

    # --- статистика по мячу ---
    print(f"\nСканирую мяч: {BALL_SCAN_FRAMES} кадров с шагом {BALL_SCAN_STRIDE}...")
    found = 0
    confs = []
    heights = Counter()

    for i in range(BALL_SCAN_FRAMES):
        frame = grab(cap, i * BALL_SCAN_STRIDE)
        if frame is None:
            break
        result = model.predict(
            frame, imgsz=IMGSZ, device=device, classes=[BALL],
            conf=CONF_BALL, verbose=False,
        )[0]
        if len(result.boxes):
            found += 1
            for box in result.boxes:
                confs.append(float(box.conf))
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
                heights[y2 - y1] += 1

    rate = found / BALL_SCAN_FRAMES * 100
    print(f"мяч найден на {found}/{BALL_SCAN_FRAMES} кадров ({rate:.0f}%)")
    if confs:
        print(f"уверенность: медиана {np.median(confs):.2f}, максимум {max(confs):.2f}")
        sizes = sorted(heights.elements())
        print(f"размер мяча в пикселях: медиана {int(np.median(sizes))}, разброс {min(sizes)}-{max(sizes)}")
    else:
        print("ни одной детекции мяча")

    cap.release()


if __name__ == "__main__":
    main()
