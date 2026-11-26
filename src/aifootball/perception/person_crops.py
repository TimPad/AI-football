"""Кадры фрагмента для признаков внешности.

Годная рамка: игрок или вратарь на площадке, высота не меньше MIN_H_PX, не ближе EDGE_PX к краю кадра, чужие рамки
того же кадра закрывают меньше MAX_COVER её площади, кадр привязан к полю (у поворотной камеры) и центр рамки не на
графике трансляции. Из годных берутся CANDIDATES самых крупных с шагом не меньше MIN_GAP_S; после вырезки остаются
KEEP самых резких (дисперсия лапласиана не ниже медианы фрагмента). Рамки tracks — в пикселях своего кадра и у
поворотной камеры тоже, кадр ищется по метке времени (FrameReader).
"""

from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import polars as pl

MIN_H_PX = 60
EDGE_PX = 8
MAX_COVER = 0.1
MIN_GAP_S = 1.0
CANDIDATES = 8
KEEP = 5


def _covered(tracks: pl.DataFrame) -> pl.DataFrame:
    """cover — доля рамки, закрытая самой большой чужой рамкой того же кадра."""
    boxes = tracks.select('frame_id', 'track_id', 'x1', 'y1', 'x2', 'y2')
    pairs = boxes.join(boxes, on='frame_id', suffix='_o').filter(pl.col('track_id') != pl.col('track_id_o'))
    iw = (pl.min_horizontal('x2', 'x2_o') - pl.max_horizontal('x1', 'x1_o')).clip(lower_bound=0)
    ih = (pl.min_horizontal('y2', 'y2_o') - pl.max_horizontal('y1', 'y1_o')).clip(lower_bound=0)
    area = (pl.col('x2') - pl.col('x1')) * (pl.col('y2') - pl.col('y1'))
    cover = pairs.with_columns(cover=iw * ih / area).group_by('frame_id', 'track_id').agg(pl.col('cover').max())
    return tracks.join(cover, on=['frame_id', 'track_id'], how='left').with_columns(pl.col('cover').fill_null(0.0))


def pick_frames(
    tracks: pl.DataFrame, frame_size: tuple[int, int], usable_frames=None, overlay=()
) -> dict[int, list[dict]]:
    """{трек: [{ts, frame_id, box}]} — до CANDIDATES годных рамок, самые крупные с шагом MIN_GAP_S."""
    w, h = frame_size
    t = tracks.filter(pl.col('in_pitch') & pl.col('role').is_in(['player', 'goalkeeper']))
    if usable_frames is not None:
        t = t.filter(pl.col('frame_id').is_in(list(usable_frames)))
    for x1, y1, x2, y2 in overlay:
        cx, cy = (pl.col('x1') + pl.col('x2')) / 2 / w, (pl.col('y1') + pl.col('y2')) / 2 / h
        t = t.filter(~(cx.is_between(x1, x2) & cy.is_between(y1, y2)))
    t = _covered(t).filter(
        (pl.col('y2') - pl.col('y1') >= MIN_H_PX)
        & (pl.col('x1') >= EDGE_PX)
        & (pl.col('y1') >= EDGE_PX)
        & (pl.col('x2') <= w - EDGE_PX)
        & (pl.col('y2') <= h - EDGE_PX)
        & (pl.col('cover') < MAX_COVER)
    )
    out = {}
    ranked = t.with_columns(height=pl.col('y2') - pl.col('y1')).sort(
        ['track_id', 'height', 'ts'], descending=[False, True, False]
    )
    for (tid,), g in ranked.group_by('track_id', maintain_order=True):
        chosen = []
        for r in g.iter_rows(named=True):
            if all(abs(r['ts'] - c['ts']) >= MIN_GAP_S for c in chosen):
                chosen.append({'ts': r['ts'], 'frame_id': r['frame_id'], 'box': [r['x1'], r['y1'], r['x2'], r['y2']]})
                if len(chosen) == CANDIDATES:
                    break
        if chosen:
            out[int(tid)] = chosen
    return out


def sharpness(image: np.ndarray) -> float:
    return float(cv2.Laplacian(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def extract_crops(video: Path, picks: dict[int, list[dict]]) -> dict[int, list[np.ndarray]]:
    """Вырезки рамок по метке времени; у трека остаются KEEP самых резких не ниже его медианы."""
    from aifootball.perception.frames import FrameReader

    requests = sorted((p['ts'], tid, p['box']) for tid, ps in picks.items() for p in ps)
    crops = defaultdict(list)
    with FrameReader(Path(video)) as reader:
        for ts, tid, (x1, y1, x2, y2) in requests:
            frame = reader.read(ts)
            if frame is None:
                continue
            crop = frame[int(y1) : int(y2), int(x1) : int(x2)]
            if crop.size:
                crops[tid].append(crop.copy())
    out = {}
    for tid, images in crops.items():
        values = [sharpness(c) for c in images]
        middle = float(np.median(values))
        ranked = sorted(zip(values, range(len(images))), key=lambda x: (-x[0], x[1]))
        out[tid] = [images[i] for v, i in ranked if v >= middle][:KEEP]
    return out
