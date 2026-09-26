"""Набор для дообучения детектора мяча из ручной разметки (tools.label_ball) в формате YOLO.

    python -m aifootball.tools.ball_dataset --video V --venue DIR --labels ball_train.parquet --out data/datasets/<имя>

Клик задаёт только центр мяча; диаметр берётся из «карты роста» игроков: рост человека
в пикселях как функция места в кадре, мяч ≈ рост / 6.7 (камера сверху сплющивает стоящих
людей, а шар — нет; множитель замерен по мячам, найденным YOLO точно).
Всё дальше margin_px за контуром поля закрашивается — так же нужно делать при распознавании:
иначе запасные мячи у скамейки учат модель, что мяч — это «не мяч».
Кадры «не видно» и кадры с мячом в закрашенной зоне пропускаются, кадры «нет в кадре»
идут пустыми примерами.
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import polars as pl
import yaml

from aifootball import schemas
from aifootball.perception.ball_detect import mask_outside_pitch, pitch_keep_mask
from aifootball.venue import load_venue

HEIGHT_PER_BALL = 6.7
MIN_PERSONS_FOR_MAP = 12  # меньше — карту не строим, берём медианный рост


def fit_person_height(persons: pl.DataFrame) -> np.ndarray:
    """Коэффициенты квадратичной «карты роста» h(x, y) по точкам касания пола.

    Сидящие, наклонённые и склеенные боксы дают выбросы — отбрасываем их итеративно.
    """
    fx = ((persons["x1"] + persons["x2"]) / 2).to_numpy().astype(float)
    fy = persons["y2"].to_numpy().astype(float)
    h = (persons["y2"] - persons["y1"]).to_numpy().astype(float)
    if len(h) < MIN_PERSONS_FOR_MAP:
        return np.array([np.median(h), 0, 0, 0, 0, 0])
    keep = np.ones(len(h), dtype=bool)
    for _ in range(5):
        coef, *_ = np.linalg.lstsq(_design(fx[keep], fy[keep]), h[keep], rcond=None)
        resid = h - _design(fx, fy) @ coef
        spread = max(np.median(np.abs(resid[keep])) * 1.48, 0.5)
        keep = np.abs(resid) < 2.5 * spread
    return coef


def ball_diameter_px(coef: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return (_design(np.asarray(x, float), np.asarray(y, float)) @ coef) / HEIGHT_PER_BALL


def yolo_label(x: float, y: float, diameter: float, width: int, height: int, min_px: float = 0.0) -> str:
    """Строка разметки YOLO (класс 0 — мяч), бокс обрезан по кадру.

    min_px — бокс не меньше этого: у мяча в 10 px почти нет ячеек сетки YOLO внутри, и сигнал
    «здесь мяч» тонет в десятках тысяч фоновых ячеек. Центр от этого не меняется.
    """
    r = max(diameter, min_px) / 2
    x1, x2 = max(0.0, x - r), min(float(width), x + r)
    y1, y2 = max(0.0, y - r), min(float(height), y + r)
    return (f"0 {(x1 + x2) / 2 / width:.6f} {(y1 + y2) / 2 / height:.6f} "
            f"{(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}")


def crop_around(x: float, y: float, tile: int, width: int, height: int, edge_px: int, seed: int) -> tuple[int, int]:
    """Левый верхний угол вырезки tile x tile, в которой мяч в случайном месте, но не ближе
    edge_px к её краю (если позволяет кадр)."""
    rng = np.random.default_rng(seed)

    def origin(c: float, size: int) -> int:
        lo, hi = c - tile + edge_px, c - edge_px
        lo, hi = max(0.0, lo), min(float(size - tile), hi)
        return int(rng.uniform(lo, hi)) if hi > lo else int(min(max(c - tile / 2, 0), size - tile))

    return origin(x, width), origin(y, height)


def crop_away_from(x: float | None, y: float | None, keep: np.ndarray, tile: int, seed: int,
                   tries: int = 300, pad: int = 20) -> tuple[int, int]:
    """Вырезка без мяча, по возможности хотя бы наполовину на поле (keep > 0)."""
    rng = np.random.default_rng(seed)
    h, w = keep.shape
    integral = cv2.integral((keep > 0).astype(np.uint8))
    best, best_share = (0, 0), -1.0
    for _ in range(tries):
        x0, y0 = int(rng.integers(0, w - tile + 1)), int(rng.integers(0, h - tile + 1))
        if x is not None and x0 - pad <= x <= x0 + tile + pad and y0 - pad <= y <= y0 + tile + pad:
            continue
        share = (integral[y0 + tile, x0 + tile] - integral[y0, x0 + tile]
                 - integral[y0 + tile, x0] + integral[y0, x0]) / tile ** 2
        if share >= 0.5:
            return x0, y0
        if share > best_share:
            best, best_share = (x0, y0), share
    return best


def time_blocks_split(frame_ids: list[int], val_fraction: float, blocks: int) -> tuple[list[int], list[int]]:
    """Делит кадры на блоки подряд по времени и отдаёт в проверку целые блоки.

    Соседние кадры почти одинаковы: раздай их вперемешку — проверка покажет запоминание,
    а не умение находить мяч.
    """
    ids = sorted(frame_ids)
    parts = np.array_split(np.array(ids), blocks)
    n_val = max(1, round(blocks * val_fraction))
    step = blocks / n_val
    val_blocks = {int(step * (i + 0.5)) for i in range(n_val)}
    val = [int(f) for i, part in enumerate(parts) if i in val_blocks for f in part]
    train = [f for f in ids if f not in set(val)]
    return train, val


def export_dataset(
    video: Path,
    venue_root: Path,
    labels: pl.DataFrame,
    persons: pl.DataFrame,
    out: Path,
    val_fraction: float = 0.15,
    blocks: int = 20,
    margin_px: int = 80,
    tile: int | None = None,
    min_box_px: float = 0.0,
) -> dict:
    """tile — вместо целого кадра писать вырезки tile x tile в полном разрешении: кадр с мячом
    даёт вырезку с мячом (_b) и без него (_n), кадр «нет в кадре» — одну без мяча (_n)."""
    venue = load_venue(venue_root)
    polygon = venue.require_polygon()
    coef = fit_person_height(persons)
    cap = cv2.VideoCapture(str(video))
    keep = pitch_keep_mask((int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))),
                           polygon, margin_px)

    def in_kept_area(row) -> bool:
        if row["status"] != "visible":
            return True
        x = min(max(int(row["x"]), 0), keep.shape[1] - 1)
        y = min(max(int(row["y"]), 0), keep.shape[0] - 1)
        return keep[y, x] > 0

    usable = labels.filter(pl.col("status") != "hidden").sort("frame_id")
    by_frame = {r["frame_id"]: r for r in usable.iter_rows(named=True) if in_kept_area(r)}
    train, val = time_blocks_split(list(by_frame), val_fraction, blocks)
    split_of = {f: "train" for f in train} | {f: "val" for f in val}
    for split in ("train", "val"):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)

    balls = 0
    for frame_id, row in by_frame.items():
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"{video}: не читается кадр {frame_id}")
        h, w = frame.shape[:2]
        masked = mask_outside_pitch(frame, polygon, margin_px)
        visible = row["status"] == "visible"
        d = float(ball_diameter_px(coef, [row["x"]], [row["y"]])[0]) if visible else 0.0
        name = f"f{frame_id:06d}"
        if tile is None:
            samples = [(name, masked, yolo_label(row["x"], row["y"], d, w, h, min_box_px) if visible else None)]
        else:
            samples = []
            if visible:
                x0, y0 = crop_around(row["x"], row["y"], tile, w, h, edge_px=max(int(d), 16), seed=frame_id)
                samples.append((f"{name}_b", masked[y0:y0 + tile, x0:x0 + tile],
                                yolo_label(row["x"] - x0, row["y"] - y0, d, tile, tile, min_box_px)))
            x0, y0 = crop_away_from(row["x"] if visible else None, row["y"] if visible else None, keep, tile,
                                    seed=frame_id + 1)
            samples.append((f"{name}_n", masked[y0:y0 + tile, x0:x0 + tile], None))
        split = split_of[frame_id]
        for sample_name, image, label in samples:
            cv2.imwrite(str(out / "images" / split / f"{sample_name}.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 95])
            (out / "labels" / split / f"{sample_name}.txt").write_text(label + "\n" if label else "")
        balls += int(visible)
    cap.release()

    data = {"path": str(out.resolve()), "train": "images/train", "val": "images/val", "names": {0: "ball"}}
    (out / "data.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return {
        "train": len(train), "val": len(val), "balls": balls,
        "skipped_hidden": labels.height - usable.height,
        "skipped_outside": usable.height - len(by_frame),
        "height_coef": [round(float(c), 4) for c in coef],
    }


def detect_persons(video: Path, frame_ids: list[int], weights: Path, imgsz: int) -> pl.DataFrame:
    """Люди на размечаемых кадрах — для карты роста. Берём уверенные боксы."""
    from ultralytics import YOLO

    from aifootball.perception.detect import pick_device

    model = YOLO(str(weights))
    device = pick_device()
    cap = cv2.VideoCapture(str(video))
    rows = []
    for frame_id in frame_ids:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        ok, frame = cap.read()
        res = model.predict(frame, imgsz=imgsz, device=device, classes=[0], conf=0.5, verbose=False)[0]
        for (x1, y1, x2, y2), conf in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.conf.cpu().numpy()):
            rows.append({"frame_id": frame_id, "ts": 0.0, "cls": "person", "x1": float(x1), "y1": float(y1),
                         "x2": float(x2), "y2": float(y2), "conf": float(conf),
                         "torso_l": np.nan, "torso_a": np.nan, "torso_b": np.nan})
    cap.release()
    return pl.DataFrame(rows, schema=schemas.DETECTIONS)


def _design(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x, y = x / 1000, y / 1000
    return np.column_stack([np.ones_like(x), x, y, x * x, x * y, y * y])


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--venue", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--models", type=Path, default=Path("models"))
    parser.add_argument("--val", type=float, default=0.15, help="доля кадров на проверку (целыми блоками)")
    parser.add_argument("--blocks", type=int, default=20)
    parser.add_argument("--margin", type=int, default=80, help="запас за контуром поля, px")
    parser.add_argument("--tile", type=int, default=None, help="писать вырезки tile x tile в полном разрешении")
    parser.add_argument("--min-box", type=float, default=0.0, help="бокс мяча не меньше, px")
    args = parser.parse_args(argv)

    venue = load_venue(args.venue)
    labels = schemas.read(args.labels, "ball_labels")
    frame_ids = labels["frame_id"].to_list()
    print(f"люди на {len(frame_ids)} кадрах для карты роста...", file=sys.stderr)
    persons = detect_persons(args.video, frame_ids, args.models / venue.model, venue.imgsz)
    from aifootball.geometry.polygons import points_in_polygon

    feet = np.column_stack([((persons["x1"] + persons["x2"]) / 2).to_numpy(), persons["y2"].to_numpy()])
    persons = persons.filter(pl.Series(points_in_polygon(feet, venue.require_polygon())))
    info = export_dataset(args.video, args.venue, labels, persons, args.out, args.val, args.blocks, args.margin, args.tile,
                          args.min_box)
    print(f"набор -> {args.out}: обучение {info['train']} кадров, проверка {info['val']}, мячей {info['balls']}, "
          f"пропущено «не видно» {info['skipped_hidden']}, мяч в закрашенной зоне {info['skipped_outside']}")


if __name__ == "__main__":
    main()
