"""L1: детекция людей и мяча по видео -> detections.parquet."""

from dataclasses import dataclass
import sys
import time
from collections.abc import Callable
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


@dataclass(frozen=True)
class DetectionBatch:
    detections: pl.DataFrame
    frame_ids: tuple[int, ...]
    timestamps: tuple[float, ...]


def detect_batches(video, venue, weights, *, batch_size=16, start_ms=0, end_ms=None,
                   progress_every=250, ball_detector=None):
    """Load weights once, retaining sampled empty frames as coverage metadata."""
    if not weights.exists():
        raise FileNotFoundError(f"нет весов модели: {weights}")
    if type(batch_size) is not int or not 1 <= batch_size <= 256:
        raise ValueError('Неверный размер пакета детекции')
    from ultralytics import YOLO
    model = YOLO(str(weights))
    device = pick_device()
    classes = [PERSON] if ball_detector else list(CLASS_NAMES)
    conf = venue.conf_person if ball_detector else min(venue.conf_person, venue.conf_ball)
    started = time.perf_counter()
    batch_meta = []

    def process(items):
        rows = []
        results = model.predict([item[2] for item in items], imgsz=venue.imgsz, device=device,
                                classes=classes, conf=conf, verbose=False)
        if len(results) != len(items):
            raise ValueError('Детектор вернул неполный пакет кадров')
        for (frame_id, ts, frame), result in zip(items, results):
            boxes = result.boxes
            rows.extend(boxes_to_rows(frame_id, ts, frame, boxes.xyxy.cpu().numpy(),
                boxes.cls.cpu().numpy(), boxes.conf.cpu().numpy(), venue.conf_person, venue.conf_ball))
            if ball_detector:
                ball_xyxy, ball_conf = ball_detector(frame)
                rows.extend(boxes_to_rows(frame_id, ts, frame, ball_xyxy, np.full(len(ball_conf), BALL),
                                         ball_conf, venue.conf_person, venue.conf_ball))
        detections = pl.DataFrame(rows, schema=schemas.DETECTIONS) if rows else schemas.empty('detections')
        return DetectionBatch(detections, tuple(item[0] for item in items), tuple(item[1] for item in items))

    total_frames = 0
    for frame_id, ts, frame in iter_frames(video, venue.target_fps, expected_width=venue.frame_width,
            expected_height=venue.frame_height, start_ms=start_ms, end_ms=end_ms):
        batch_meta.append((frame_id, ts, frame)); total_frames += 1
        if len(batch_meta) >= batch_size:
            yield process(batch_meta); batch_meta.clear()
            if progress_every and total_frames % progress_every == 0:
                elapsed = time.perf_counter() - started
                print(f"  {total_frames} кадров, {ts / 60:.1f} мин видео, {total_frames / elapsed:.1f} кадр/с", file=sys.stderr)
    if batch_meta:
        yield process(batch_meta)


def detect_video(video: Path, venue: Venue, weights: Path, batch_size: int = 16,
                 progress_every: int = 250, ball_detector=None) -> pl.DataFrame:
    batches = [batch.detections for batch in detect_batches(video, venue, weights, batch_size=batch_size,
               progress_every=progress_every, ball_detector=ball_detector)]
    return pl.concat(batches) if batches else schemas.empty('detections')
