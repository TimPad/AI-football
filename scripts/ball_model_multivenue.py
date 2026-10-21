"""Общая модель мяча для нескольких залов: набор, обучение, кандидаты, разметка зала. Отчёт — docs/2026-10-20-multi-venue-ball-model.md.

    .venv/bin/python scripts/ball_model_multivenue.py crops --source old DIR --source rf3 DIR ... --out data/datasets/ball-multi-v1
    .venv/bin/python scripts/ball_model_multivenue.py add-hall --base DIR --tiles DIR --labels L --candidates C --video V --venue DIR --out DIR
    .venv/bin/python scripts/ball_model_multivenue.py train --data DATA_YAML --base yolo26s.pt --out output/ball-multi/v26
    .venv/bin/python scripts/ball_model_multivenue.py candidates --weights W --video V --venue DIR --out cand.parquet
    .venv/bin/python scripts/ball_model_multivenue.py labeling --candidates C --venue DIR --out data/gt/<отрезок> [--count 300]
    .venv/bin/python scripts/ball_model_multivenue.py replace --match DIR --candidates C --venue DIR

crops — вырезки 640x640 в исходном разрешении (мяч сохраняет размер в пикселях), рамка мяча не меньше 32 px, как
tools.ball_dataset --min-box 32; источник — набор YOLO в раскладке images/<split> или <split>/images (Roboflow).
add-hall — к набору добавляются вырезки зала из tools.ball_dataset --tile 640 --min-box 32 и «трудные без мяча»:
вырезка вокруг самого уверенного ложного кандидата модели на размеченном кадре (рука зрителя, номер на футболке).
candidates — все кандидаты мяча от 0.05 на каждом кадре (BallDetector, как в пайплайне).
labeling — кадры для tools.label_ball --frames и подсказки --hints: половина равномерно, половина трудных для модели.
replace — заменить мяч в готовом прогоне на кандидатов (порог conf_ball зала); игроки не пересчитываются.
"""
import argparse
import json
import os
import random
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from eval_ball_multivenue import centers_of, on_pitch_metres, pipeline_pick, top_per_frame  # noqa: E402

from aifootball import schemas  # noqa: E402
from aifootball.perception.ball_detect import mask_outside_pitch  # noqa: E402
from aifootball.venue import load_venue  # noqa: E402

CROP, MIN_BOX = 640, 32
CANDIDATE_CONF = 0.05
HARD_CONF = 0.25
HARD_NEAR_PX = 12  # кандидат дальше от клика — не мяч
LABELING_GAP = 12  # между выбранными кадрами не меньше ~0.5 с при 25 к/с: соседние кадры почти одинаковы


def cmd_crops(args) -> None:
    rng = random.Random(0)
    if args.out.exists():
        shutil.rmtree(args.out)
    for tag, root in args.source:
        root = Path(root)
        for split, names in (('train', ('train',)), ('val', ('val', 'valid'))):
            for name in names:
                for img_dir, lab_dir in ((root / 'images' / name, root / 'labels' / name), (root / name / 'images', root / name / 'labels')):
                    if img_dir.is_dir():
                        n, balls = _crop_dir(img_dir, lab_dir, args.out, split, tag, rng)
                        print(f'{tag:>6} {split:>5}: вырезок {n}, с мячом {balls}', flush=True)
    _write_yaml(args.out)


def _crop_dir(img_dir: Path, lab_dir: Path, out: Path, split: str, tag: str, rng: random.Random) -> tuple[int, int]:
    n = balls = 0
    for p in sorted(img_dir.iterdir()):
        img = cv2.imread(str(p))
        if img is None:
            continue
        label = lab_dir / (p.stem + '.txt')
        rows = [line.split() for line in label.read_text().splitlines() if line.strip()] if label.exists() else []
        boxes = [tuple(map(float, r[1:5])) for r in rows if r[0] == '0']  # только класс «мяч»
        crop, kept = _crop_with_ball(img, boxes, rng)
        _write_sample(out, split, f'{tag}_{n:05d}', crop, kept)
        n += 1
        balls += bool(kept)
    return n, balls


def _crop_with_ball(img: np.ndarray, boxes: list, rng: random.Random):
    """Вырезка CROP x CROP с мячом в случайном месте (или случайная, если мяча нет); рамки в пикселях вырезки."""
    h, w = img.shape[:2]
    if h <= CROP and w <= CROP:
        pad = np.full((CROP, CROP, 3), 114, np.uint8)
        pad[:h, :w] = img
        return pad, [(cx * w, cy * h, bw * w, bh * h) for cx, cy, bw, bh in boxes]
    if boxes:
        cx, cy = boxes[rng.randrange(len(boxes))][:2]
        x0 = int(np.clip(cx * w - rng.uniform(0.15, 0.85) * CROP, 0, w - CROP))
        y0 = int(np.clip(cy * h - rng.uniform(0.15, 0.85) * CROP, 0, h - CROP))
    else:
        x0, y0 = rng.randint(0, max(0, w - CROP)), rng.randint(0, max(0, h - CROP))
    kept = [(bx * w - x0, by * h - y0, bw * w, bh * h) for bx, by, bw, bh in boxes
            if 0 <= bx * w - x0 < CROP and 0 <= by * h - y0 < CROP]
    return img[y0:y0 + CROP, x0:x0 + CROP], kept


def _write_sample(out: Path, split: str, name: str, img: np.ndarray, boxes: list) -> None:
    (out / 'images' / split).mkdir(parents=True, exist_ok=True)
    (out / 'labels' / split).mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out / 'images' / split / f'{name}.jpg'), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    lines = [f'0 {px / CROP:.6f} {py / CROP:.6f} {max(bw, MIN_BOX) / CROP:.6f} {max(bh, MIN_BOX) / CROP:.6f}' for px, py, bw, bh in boxes]
    (out / 'labels' / split / f'{name}.txt').write_text(''.join(line + '\n' for line in lines))


def _write_yaml(out: Path) -> None:
    (out / 'data.yaml').write_text(f'path: {out.resolve()}\ntrain: images/train\nval: images/val\nnames:\n  0: ball\n')


def cmd_add_hall(args) -> None:
    if args.out.exists():
        shutil.rmtree(args.out)
    base_n = _link_tree(args.base, args.out)
    tiles_n = _link_tree(args.tiles, args.out, f'{args.tag}_')
    # tools.ball_dataset пишет f<кадр>_n на каждый пригодный кадр: по нему узнаём, в какую часть попал кадр
    split_of = {int(p.stem[1:7]): split for split in ('train', 'val') for p in (args.tiles / 'images' / split).glob('f*_n.jpg')}
    venue = load_venue(args.venue)
    labels = schemas.read(args.labels, 'ball_labels').filter(pl.col('status') != 'hidden')
    cand = pl.read_parquet(args.candidates).filter(pl.col('conf') >= HARD_CONF)
    cap = cv2.VideoCapture(str(args.video))
    rng = np.random.default_rng(0)
    hard = {'train': 0, 'val': 0}
    for f, status, x, y in labels.select('frame_id', 'status', 'x', 'y').iter_rows():
        split = split_of.get(f)
        if split is None:  # кадр отброшен tools.ball_dataset: мяч в закрашенной зоне
            continue
        c = cand.filter(pl.col('frame_id') == f).sort('conf', descending=True)
        cx, cy = centers_of(c).T if len(c) else (np.zeros(0), np.zeros(0))
        wrong = np.ones(len(c), bool) if status == 'absent' else np.hypot(cx - x, cy - y) > HARD_NEAR_PX
        if not wrong.any():
            continue
        i = int(np.argmax(wrong))
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        masked = mask_outside_pitch(frame, venue.require_polygon(), venue.ball_margin_px)
        x0 = int(np.clip(cx[i] - rng.uniform(0.2, 0.8) * CROP, 0, w - CROP))
        y0 = int(np.clip(cy[i] - rng.uniform(0.2, 0.8) * CROP, 0, h - CROP))
        # настоящий мяч, попавший в вырезку, размечен: иначе модель училась бы, что он — фон
        ball = [(x - x0, y - y0, MIN_BOX, MIN_BOX)] if status == 'visible' and x0 <= x < x0 + CROP and y0 <= y < y0 + CROP else []
        _write_sample(args.out, split, f'{args.tag}_f{f:06d}_h', masked[y0:y0 + CROP, x0:x0 + CROP], ball)
        hard[split] += 1
    cap.release()
    _write_yaml(args.out)
    print(f'основа {base_n} вырезок; зал: {tiles_n} из tools.ball_dataset + трудных без мяча {hard} -> {args.out}')


def _link_tree(src: Path, dst: Path, prefix: str = '') -> int:
    """Жёсткие ссылки вместо копий: набор в гигабайт не дублируется."""
    n = 0
    for split in ('train', 'val'):
        for kind in ('images', 'labels'):
            (dst / kind / split).mkdir(parents=True, exist_ok=True)
            for p in (src / kind / split).iterdir():
                os.link(p, dst / kind / split / f'{prefix}{p.name}')
                n += kind == 'images'
    return n


def cmd_train(args) -> None:
    from ultralytics import YOLO

    # Рецепт v1: без смешанной точности и без разгона сдвига — иначе на MPS cls_loss уходил в NaN
    YOLO(str(args.models / args.base)).train(
        data=str(args.data), imgsz=CROP, epochs=args.epochs, patience=8, batch=16, workers=4, device='mps', amp=False,
        warmup_bias_lr=0.0, close_mosaic=5, project=str(args.out.parent), name=args.out.name, exist_ok=True, plots=False, seed=0)


def cmd_candidates(args) -> None:
    from aifootball.perception.ball_detect import BallDetector
    from aifootball.perception.detect import pick_device

    venue = load_venue(args.venue)
    cap = cv2.VideoCapture(str(args.video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    shape = (int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
    det = BallDetector(args.weights, venue.require_polygon(), shape, venue.ball_tile, venue.ball_margin_px, CANDIDATE_CONF, pick_device())
    rows, f, started = [], 0, time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        boxes, confs = det(frame)
        rows += [(f, *map(float, b), float(c)) for b, c in zip(boxes, confs)]
        f += 1
        if f % 500 == 0:
            print(f'{f}/{total} кадров, {time.time() - started:.0f} с', flush=True)
    cap.release()
    schema = {'frame_id': pl.Int32, 'x1': pl.Float64, 'y1': pl.Float64, 'x2': pl.Float64, 'y2': pl.Float64, 'conf': pl.Float64}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows, schema=schema, orient='row').write_parquet(args.out)
    print(f'{f} кадров, кандидатов {len(rows)} -> {args.out}')


def cmd_labeling(args) -> None:
    """Трудные кадры: самый уверенный кандидат отброшен правилами (обманулась), лучший 0.1–0.5 (сомневается),
    ни одного от 0.1 (не видит). Подсказка — мяч, которого выбрал бы пайплайн."""
    venue = load_venue(args.venue)
    raw = pl.read_parquet(args.candidates)
    total = int(raw['frame_id'].max()) + 1
    c = on_pitch_metres(raw, venue)
    pick = pipeline_pick(c, venue.target_fps)
    xy = centers_of(pick)
    hints = pick.select('frame_id', 'conf').with_columns(x=pl.Series(xy[:, 0]), y=pl.Series(xy[:, 1]))

    best_conf = dict(top_per_frame(c).select('frame_id', 'conf').iter_rows())
    picked = {f: (x1, y1) for f, x1, y1 in pick.select('frame_id', 'x1', 'y1').iter_rows()}
    top = top_per_frame(c.filter(pl.col('conf') >= HARD_CONF))
    pools = {
        'обманулась': [f for f, x1, y1 in top.select('frame_id', 'x1', 'y1').iter_rows() if picked.get(f) != (x1, y1)],
        'сомневается': [f for f, v in best_conf.items() if 0.1 <= v < 0.5 and f not in picked],
        'не видит': [f for f in range(total) if best_conf.get(f, 0.0) < 0.1],
    }
    print(f'кадров {total}, подсказка в {len(pick)}; трудные: ' + ', '.join(f'{k} {len(v)}' for k, v in pools.items()))

    chosen = {int(v) for v in np.linspace(0, total - 1, args.count // 2).round()}
    rng = random.Random(0)
    pools = {k: rng.sample(v, len(v)) for k, v in pools.items()}
    got = dict.fromkeys(pools, 0)
    while len(chosen) < args.count and any(pools.values()):
        for name, pool in pools.items():
            taken = np.array(sorted(chosen))
            while pool:
                f = pool.pop()
                if np.abs(taken - f).min() >= LABELING_GAP:
                    chosen.add(f)
                    got[name] += 1
                    break
            if len(chosen) >= args.count:
                break
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'frames.txt').write_text(''.join(f'{f}\n' for f in sorted(chosen)))
    hints.write_parquet(args.out / 'hints.parquet')
    print(f'выбрано {len(chosen)}: трудных {got}, с подсказкой {sum(f in picked for f in chosen)} -> {args.out}')


def cmd_replace(args) -> None:
    venue = load_venue(args.venue)
    meta = json.loads((args.match / 'meta.json').read_text())
    det = schemas.read(args.match / 'detections.parquet', 'detections')
    backup = args.match / f"detections_{Path(meta.get('ball_model') or 'none/x').parent.name}.parquet"
    if not backup.exists():
        shutil.copy2(args.match / 'detections.parquet', backup)
    persons = det.filter(pl.col('cls') != 'ball')
    frames = det.select('frame_id', 'ts').unique().sort('frame_id')
    c = pl.read_parquet(args.candidates).filter(pl.col('conf') >= venue.conf_ball)
    ts = np.interp(c['frame_id'].to_numpy(), frames['frame_id'].to_numpy(), frames['ts'].to_numpy())
    balls = c.with_columns(ts=pl.Series(ts), cls=pl.lit('ball'), torso_l=pl.lit(np.nan), torso_a=pl.lit(np.nan),
                           torso_b=pl.lit(np.nan)).select(persons.columns).cast(dict(persons.schema))
    schemas.write(pl.concat([persons, balls]).sort('frame_id'), args.match / 'detections.parquet', 'detections')
    meta.update(ball_model=venue.ball_model, conf_ball=venue.conf_ball, ball_replaced='мяч заменён кандидатами; игроки прежние')
    (args.match / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f'{args.match.name}: мячей было {det.filter(pl.col("cls") == "ball").height}, стало {len(balls)}; копия -> {backup.name}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('crops')
    p.add_argument('--source', nargs=2, action='append', metavar=('TAG', 'DIR'), required=True)
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('add-hall')
    for name in ('base', 'tiles', 'labels', 'candidates', 'video', 'venue', 'out'):
        p.add_argument(f'--{name}', type=Path, required=True)
    p.add_argument('--tag', default='hall')
    p = sub.add_parser('train')
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--base', default='yolo26s.pt')
    p.add_argument('--models', type=Path, default=Path('models'))
    p.add_argument('--epochs', type=int, default=30)
    p = sub.add_parser('candidates')
    for name in ('weights', 'video', 'venue', 'out'):
        p.add_argument(f'--{name}', type=Path, required=True)
    p = sub.add_parser('labeling')
    for name in ('candidates', 'venue', 'out'):
        p.add_argument(f'--{name}', type=Path, required=True)
    p.add_argument('--count', type=int, default=300)
    p = sub.add_parser('replace')
    for name in ('match', 'candidates', 'venue'):
        p.add_argument(f'--{name}', type=Path, required=True)
    args = parser.parse_args()
    {'crops': cmd_crops, 'add-hall': cmd_add_hall, 'train': cmd_train, 'candidates': cmd_candidates,
     'labeling': cmd_labeling, 'replace': cmd_replace}[args.cmd](args)


if __name__ == '__main__':
    main()
