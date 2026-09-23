"""L1: детекция людей и мяча по видео -> detections.parquet."""

import math
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl
import torch

from aifootball import schemas
from aifootball.perception.color import NAN3, torso_lab
from aifootball.perception.frames import iter_frames
from aifootball.venue import Venue

PERSON = 0  # COCO 'person'
BALL = 32  # COCO 'sports ball'
CLASS_NAMES = {PERSON: "person", BALL: "ball"}


def pick_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def boxes_to_rows(
    frame_id: int,
    ts: float,
    frame: np.ndarray,
    xyxy: np.ndarray,
    classes: np.ndarray,
    confs: np.ndarray,
    conf_person: float,
    conf_ball: float,
) -> list[dict]:
    """Переводит выход детектора в строки detections.parquet.

    Порог у каждого класса свой: модель вызывается с минимальным из них,
    чтобы не потерять мяч, а людей отсекаем здесь по их собственному порогу.
    """
    thresholds = {PERSON: conf_person, BALL: conf_ball}
    rows = []
    for box, cls, conf in zip(xyxy, classes, confs):
        cls, conf = int(cls), float(conf)
        if cls not in CLASS_NAMES or conf < thresholds[cls]:
            continue
        l, a, b = torso_lab(frame, box) if cls == PERSON else NAN3
        x1, y1, x2, y2 = (float(v) for v in box)
        rows.append({
            "frame_id": frame_id, "ts": ts, "cls": CLASS_NAMES[cls],
            "x1": x1, "y1": y1, "x2": x2, "y2": y2, "conf": conf,
            "torso_l": l, "torso_a": a, "torso_b": b,
        })
    return rows


def detect_video(video: Path, venue: Venue, weights: Path, progress_every: int = 250) -> pl.DataFrame:
    if not weights.exists():
        raise FileNotFoundError(f"нет весов модели: {weights}")
    from ultralytics import YOLO  # тяжёлый импорт — только когда реально детектируем

    model = YOLO(str(weights))
    device = pick_device()
    conf = min(venue.conf_person, venue.conf_ball)
    rows: list[dict] = []
    started = time.perf_counter()

    for n, (frame_id, ts, frame) in enumerate(iter_frames(video, venue.target_fps), start=1):
        result = model.predict(
            frame, imgsz=venue.imgsz, device=device, classes=list(CLASS_NAMES), conf=conf, verbose=False
        )[0]
        boxes = result.boxes
        rows.extend(boxes_to_rows(
            frame_id, ts, frame,
            boxes.xyxy.cpu().numpy(), boxes.cls.cpu().numpy(), boxes.conf.cpu().numpy(),
            venue.conf_person, venue.conf_ball,
        ))
        if n % progress_every == 0:
            elapsed = time.perf_counter() - started
            print(f"  {n} кадров, {ts / 60:.1f} мин видео, {n / elapsed:.1f} кадр/с", file=sys.stderr)

    if not rows:
        return schemas.empty("detections")
    return pl.DataFrame(rows, schema=schemas.DETECTIONS)
