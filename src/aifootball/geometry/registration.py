"""Привязка кадров поворотной камеры (пан, наклон, зум) к эталонному кадру профиля.

Камера трансляции стоит на штативе: поворачивается и меняет зум, но не перемещается. Тогда любые два кадра
связаны гомографией H = K₂·R·K₁⁻¹, точной для всех точек сцены, и сверка по фону (стены, баннеры, разметка)
переводит кадр в плоскость эталонного кадра, где размечена гомография «пиксели -> метры». Дальше конвейер
работает как с неподвижной камерой, смотрящей из эталона («виртуальная неподвижная камера»).

Как привязываются кадры (замеры на матче ВШЭ — docs/2026-11-22-moving-camera.md):
- цепочка «кадр к предыдущему» уплывает (медиана 47 px, худшие — метры), поэтому каждый кадр сверяется
  напрямую с опорным кадром; цепочка лишь подсказывает, какие опорные ближе, и при малом числе
  согласных точек берётся лучший из них;
- новый опорный кадр — когда вид перекрывается с известными меньше чем на KEY_OVERLAP или согласных
  с текущим опорным становится мало (KEY_REFRESH_INLIERS);
- после долгой потери (смена плана, крупный план, графика) поиск идёт по всем опорным, а если вид так
  и не найден — начинается новый «остров» опорных кадров;
- в конце опорные кадры сверяются попарно и вместе с эталоном подгоняются совместно (как при сшивке
  панорамы): одна неудачная сверка иначе ведёт в сторону все кадры своего опорного.
Повторы — та же камера, и геометрия склейку не замечает: их находит образец плашки повтора.
"""

import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import polars as pl

from aifootball import schemas

WORK_WIDTH = 960  # кадр уменьшается для поиска особых точек; гомография пересчитывается в полное разрешение
N_FEATURES = 2500
RATIO = 0.75  # тест Лоу для сопоставления дескрипторов
RANSAC_PX = 2.0  # в пикселях рабочего размера
MIN_FEATURES = 200  # меньше особых точек (заставка, смаз, однотонный экран) — опорным кадром не делаем
# Меньше согласных точек — сверке не верим. Кадр, сверенный с опорным хотя бы по стольким точкам, привязан:
# на ВШЭ кадры с 40–59 точками расходятся с прототипом на 4–5 см по медиане, как и с 60–120.
MIN_INLIERS = 40
KEY_MIN_INLIERS = 100  # новый опорный — только из уверенно привязанного кадра (смазанный кадр — плохой опорный)
KEY_OVERLAP = 0.6
# Согласных с опорным всё меньше, хотя вид ещё перекрывается (мало деталей, зум): новый опорный, пока кадр
# привязан надёжно, иначе следующие кадры держатся за опорный десятками точек на краю и ошибаются на пиксели.
KEY_REFRESH_INLIERS = 150
KEY_MAX_OVERLAP = 0.85  # на бедном деталями виде согласных всегда мало: опорные не плодим на одном месте
# С последним опорным мало точек — сверяем и с остальными ближайшими и берём лучший: иначе кадры держатся
# за давний опорный десятками точек (на ВШЭ около 30:15 — 75 точек и ошибка около метра при 330 у соседнего).
ENOUGH_INLIERS = KEY_REFRESH_INLIERS
RELOC_AFTER = 10  # кадров подряд без сверки — ищем по всем опорным раз в столько кадров
NEW_ISLAND_AFTER_S = 3.0  # вид не находится столько секунд — начинаем новый остров опорных
LINK_MIN_INLIERS = 60  # связь опорных разных островов или с эталоном
FALSE_LINK_PX = 50.0  # связь внутри острова расходится с цепочкой больше — ложное совпадение похожих видов
BAD_LINK_PX = 10.0  # после подгонки связь с такой невязкой отбрасывается, подгонка повторяется
LINK_POINTS = 200  # точек на связь в подгонке
REPLAY_SCORE = 0.45  # корреляция с образцом плашки: на ВШЭ в повторах ≥ 0.70, вне повторов ≤ 0.18
REPLAY_SEARCH_PX = 8
REPLAY_BRIDGE_S = 1.0  # плашка мигает: короткие пропуски внутри повтора заполняются
REPLAY_PAD_S = 0.5  # склейка с повтором чуть раньше появления плашки и чуть позже её ухода

STATUSES = ('ok', 'weak', 'lost', 'replay')
VERSION = 'ptz-registration-v1'  # входит в отпечаток обработки: смена алгоритма не смешивается с сохранённой
MIN_LINKED_SHARE = 0.5  # привязано меньше — координат слишком мало для отчёта


@dataclass
class _Key:
    frame_id: int
    points: np.ndarray
    descriptors: np.ndarray
    H: np.ndarray  # рабочие пиксели опорного -> плоскость его острова
    island: int


@dataclass
class _Frame:
    frame_id: int
    ts: float
    key: int = -1  # опорный, с которым кадр сверен (или последний — для кадров по прогнозу)
    inliers: int = 0
    src: str = 'lost'  # key | pred | lost
    H: np.ndarray | None = None  # рабочие пиксели кадра -> плоскость острова
    replay: bool = False


@dataclass
class Registration:
    frames: pl.DataFrame  # схема schemas.REGISTRATION
    summary: dict = field(default_factory=dict)


class _Matcher:
    def __init__(self, mask: np.ndarray):
        self.mask = mask
        self.sift = cv2.SIFT_create(N_FEATURES)
        self.bf = cv2.BFMatcher(cv2.NORM_L2)

    def features(self, gray: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
        keypoints, descriptors = self.sift.detectAndCompute(gray, self.mask)
        return np.float32([k.pt for k in keypoints]).reshape(-1, 2), descriptors

    def match(self, a, b, min_inliers=MIN_INLIERS):
        """Гомография точек a -> b, число согласных и сами согласные пары (или None)."""
        (pa, da), (pb, db) = a, b
        if da is None or db is None or len(pa) < min_inliers or len(pb) < min_inliers:
            return None
        pairs = self.bf.knnMatch(da, db, k=2)
        good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < RATIO * p[1].distance]
        if len(good) < min_inliers:
            return None
        src = pa[[m.queryIdx for m in good]]
        dst = pb[[m.trainIdx for m in good]]
        H, inliers = cv2.findHomography(src, dst, cv2.USAC_MAGSAC, RANSAC_PX, maxIters=5000, confidence=0.999)
        if H is None or inliers is None:
            return None
        keep = inliers.ravel().astype(bool)
        if keep.sum() < min_inliers:
            return None
        return H / H[2, 2], int(keep.sum()), src[keep], dst[keep]


def overlay_mask(shape: tuple[int, int], overlay: Iterable) -> np.ndarray:
    """Маска поиска особых точек: графика трансляции (доли кадра x1, y1, x2, y2) закрыта."""
    h, w = shape
    mask = np.full((h, w), 255, np.uint8)
    for x1, y1, x2, y2 in overlay:
        mask[int(round(y1 * h)) : int(round(y2 * h)), int(round(x1 * w)) : int(round(x2 * w))] = 0
    return mask


def _apply(H, points):
    points = np.asarray(points, np.float64).reshape(-1, 2)
    if len(points) == 0:
        return points
    return cv2.perspectiveTransform(points.reshape(-1, 1, 2), H).reshape(-1, 2)


def _overlap(H_cur, H_key, corners, area, symmetric=True):
    """Перекрытие кадра с опорным в изображении опорного (в плоскости острова дальние виды огромны).

    symmetric: пересечение / меньшая площадь (выбор кандидатов при разном зуме); иначе — доля текущего кадра,
    покрытая опорным (решение о новом опорном). Кадр, уходящий за плоскость опорного, — 0.
    """
    p = np.linalg.inv(H_key) @ H_cur @ np.vstack([corners.T, np.ones(4)])
    if (p[2] <= 1e-9).any():
        return 0.0
    pts = (p[:2] / p[2]).T.astype(np.float32)
    if not np.isfinite(pts).all():
        return 0.0
    try:
        inter, _ = cv2.intersectConvexConvex(pts, corners.astype(np.float32))
    except cv2.error:
        return 0.0
    own = cv2.contourArea(pts)
    if own <= 1e-6:
        return 0.0
    return float(inter / min(own, area)) if symmetric else float(inter / own)


class _Sequence:
    """Проход по кадрам: сверка с опорными, прогноз цепочкой, новые опорные и острова."""

    def __init__(self, matcher: _Matcher, shape: tuple[int, int], fps: float):
        h, w = shape
        self.matcher = matcher
        self.corners = np.float64([[0, 0], [w, 0], [w, h], [0, h]])
        self.area = float(w * h)
        self.new_island_after = max(RELOC_AFTER + 1, int(round(NEW_ISLAND_AFTER_S * fps)))
        self.keys: list[_Key] = []
        self.islands = 0
        self.prev = None
        self.prev_H = None
        self.prev_island = -1
        self.last_key = None
        self.miss = 0

    def _new_key(self, frame: _Frame, feat, H, island):
        self.keys.append(_Key(frame.frame_id, feat[0], feat[1], H, island))
        return len(self.keys) - 1

    def step(self, frame: _Frame, feat) -> _Frame:
        enough = feat[1] is not None and len(feat[0]) >= MIN_FEATURES
        island = self.prev_island
        if not self.keys:
            if enough and not frame.replay:
                island, self.islands = 0, 1
                frame.key, frame.inliers, frame.src, frame.H = (
                    self._new_key(frame, feat, np.eye(3), 0),
                    len(feat[0]),
                    'key',
                    np.eye(3),
                )
                self.last_key = frame.key
            self._remember(feat, frame.H, island if frame.H is not None else -1)
            return frame

        step = self.matcher.match(feat, self.prev) if self.prev is not None else None
        predicted = self.prev_H @ step[0] if step is not None and self.prev_H is not None else None
        same = [k for k, key in enumerate(self.keys) if key.island == island]
        if predicted is not None:
            near = sorted(same, key=lambda k: -_overlap(predicted, self.keys[k].H, self.corners, self.area))[:3]
        else:
            near = []
        candidates = ([self.last_key] if self.last_key is not None else []) + [k for k in near if k != self.last_key]
        if self.miss >= RELOC_AFTER and self.miss % RELOC_AFTER == 0:
            # Переотыскание: прогноз после сбоя мог уйти — пробуем все опорные, сначала своего острова.
            candidates = near + [k for k in same if k not in near] + [k for k in range(len(self.keys)) if k not in same]
        best = None
        for k in candidates:
            found = self.matcher.match(feat, (self.keys[k].points, self.keys[k].descriptors))
            if found is not None and (best is None or found[1] > best[1][1]):
                best = (k, found)
            if best is not None and best[1][1] >= ENOUGH_INLIERS:
                break
        if best is not None:
            k, found = best
            key = self.keys[k]
            frame.H, frame.inliers, frame.key, frame.src = key.H @ found[0], found[1], k, 'key'
            island, self.last_key, self.miss = key.island, k, 0
            same = [j for j, other in enumerate(self.keys) if other.island == island]
            covered = max(_overlap(frame.H, self.keys[j].H, self.corners, self.area, False) for j in same)
            moved_on = found[1] >= KEY_MIN_INLIERS and covered < KEY_OVERLAP
            fading = KEY_MIN_INLIERS <= found[1] < KEY_REFRESH_INLIERS and covered < KEY_MAX_OVERLAP
            if not frame.replay and (moved_on or fading):
                self.last_key = self._new_key(frame, feat, frame.H, island)  # следующий кадр — сначала с ним
        else:
            self.miss += 1
            if predicted is not None:
                frame.H, frame.src, frame.key = predicted, 'pred', self.last_key if self.last_key is not None else -1
            if self.miss >= self.new_island_after and enough and step is not None and not frame.replay:
                # Вид не находится долго, а кадр чёткий и устойчивый: начинаем новый остров.
                island, self.islands = self.islands, self.islands + 1
                frame.key = self._new_key(frame, feat, np.eye(3), island)
                frame.H, frame.inliers, frame.src, self.last_key, self.miss = (
                    np.eye(3),
                    len(feat[0]),
                    'key',
                    frame.key,
                    0,
                )
        self._remember(feat, frame.H, island if frame.H is not None else -1)
        return frame

    def _remember(self, feat, H, island):
        self.prev, self.prev_H, self.prev_island = feat, H, island


def _link_error(H_i, H_j, pi, pj):
    """Расхождение связи с текущими положениями опорных: медиана по точкам, рабочие пиксели."""
    return float(np.median(np.hypot(*(_apply(np.linalg.inv(H_j) @ H_i, pi) - pj).T)))


def _adjust(keys: list[_Key], reference, matcher: _Matcher) -> tuple[dict[int, np.ndarray], dict]:
    """Положения опорных в плоскости эталона: попарная сверка, остов от эталона, совместная подгонка.

    Возвращает {номер опорного: гомография рабочих пикселей опорного -> рабочие пиксели эталона} для
    опорных, связанных с эталоном, и сводку.
    """
    from scipy.optimize import least_squares
    from scipy.sparse import lil_matrix

    feats = [(k.points, k.descriptors) for k in keys] + [reference]
    ref = len(keys)
    island = [k.island for k in keys] + [-1]
    links, dropped_false = [], 0
    rng = np.random.default_rng(0)
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            cross = island[i] != island[j]
            found = matcher.match(feats[i], feats[j], LINK_MIN_INLIERS if cross else MIN_INLIERS)
            if found is None:
                continue
            D, n, pi, pj = found
            if not cross and _link_error(keys[i].H, keys[j].H, pi, pj) > FALSE_LINK_PX:
                dropped_false += 1  # похожие виды (две половины зала): цепочка говорит, что это разные места
                continue
            if len(pi) > LINK_POINTS:
                pick = rng.choice(len(pi), LINK_POINTS, replace=False)
                pi, pj = pi[pick], pj[pick]
            links.append((i, j, D, n, pi.astype(np.float64), pj.astype(np.float64)))

    # Начальные положения: дерево от эталона по самым сильным связям (Прим).
    pose = {ref: np.eye(3)}
    while True:
        best = None
        for i, j, D, n, _, _ in links:
            if (i in pose) != (j in pose) and (best is None or n > best[0]):
                best = (n, i, j, D)
        if best is None:
            break
        _, i, j, D = best
        if i in pose:
            pose[j] = pose[i] @ np.linalg.inv(D)  # точки j -> точки i -> эталон
        else:
            pose[i] = pose[j] @ D
    for k in pose:
        pose[k] = pose[k] / pose[k][2, 2]

    def solve(active):
        free = [k for k in sorted(pose) if k != ref]
        index = {k: n for n, k in enumerate(free)}
        if not free or not active:
            return dict(pose), np.zeros(0)

        def unpack(x):
            out = {ref: np.eye(3)}
            for k, n in index.items():
                out[k] = np.append(x[8 * n : 8 * n + 8], 1.0).reshape(3, 3)
            return out

        def residuals(x):
            P = unpack(x)
            res = []
            for i, j, _, _, pi, pj in active:
                res.append((_apply(np.linalg.inv(P[j]) @ P[i], pi) - pj).ravel())
                res.append((_apply(np.linalg.inv(P[i]) @ P[j], pj) - pi).ravel())
            return np.concatenate(res)

        rows = sum(4 * len(pi) for *_, pi, _ in active)
        sparsity = lil_matrix((rows, 8 * len(free)), dtype=int)
        row = 0
        for i, j, *_, pi, _ in active:
            for k in (i, j):
                if k in index:
                    sparsity[row : row + 4 * len(pi), 8 * index[k] : 8 * index[k] + 8] = 1
            row += 4 * len(pi)
        x0 = np.concatenate([pose[k].ravel()[:8] for k in free])
        solution = least_squares(
            residuals, x0, jac_sparsity=sparsity, loss='huber', f_scale=2.0, x_scale='jac', max_nfev=100
        )
        return unpack(solution.x), np.abs(residuals(solution.x))

    active = [link for link in links if link[0] in pose and link[1] in pose]
    P, res = solve(active)
    good = [link for link in active if _link_error(P[link[0]], P[link[1]], link[4], link[5]) <= BAD_LINK_PX]
    bad = len(active) - len(good)
    if bad:
        active = good
        P, res = solve(active)
    summary = {
        'keyframes': len(keys),
        'islands': max(island) + 1 if keys else 0,
        'keyframes_linked_to_reference': len([k for k in P if k != ref]),
        'reference_links': sum(1 for link in active if ref in link[:2]),
        'links': len(active),
        'links_dropped': dropped_false + bad,
        # Невязка связей опорных после подгонки, пиксели рабочего размера (WORK_WIDTH по ширине).
        'residual_px': {
            'median': round(float(np.median(res)), 3) if len(res) else 0.0,
            'p90': round(float(np.percentile(res, 90)), 3) if len(res) else 0.0,
        },
    }
    return {k: H for k, H in P.items() if k != ref}, summary


def _replay_score(frame_gray: np.ndarray, badge: np.ndarray, xy: tuple[int, int]) -> float:
    x, y = xy
    h, w = badge.shape
    x0, y0 = max(0, x - REPLAY_SEARCH_PX), max(0, y - REPLAY_SEARCH_PX)
    crop = frame_gray[y0 : y + h + REPLAY_SEARCH_PX, x0 : x + w + REPLAY_SEARCH_PX]
    if crop.shape[0] < h or crop.shape[1] < w:
        return 0.0
    return float(cv2.matchTemplate(crop, badge, cv2.TM_CCOEFF_NORMED).max())


def replay_flags(ts: np.ndarray, hits: np.ndarray) -> np.ndarray:
    """Кадры повторов по кадрам с плашкой: короткие пропуски заполняются, края расширяются."""
    ts, hits = np.asarray(ts, np.float64), np.asarray(hits, bool)
    out = np.zeros(len(ts), bool)
    idx = np.flatnonzero(hits)
    if not len(idx):
        return out
    runs, start = [], idx[0]
    for a, b in zip(idx, idx[1:]):
        if ts[b] - ts[a] > REPLAY_BRIDGE_S:
            runs.append((start, a))
            start = b
    runs.append((start, idx[-1]))
    for a, b in runs:
        out |= (ts >= ts[a] - REPLAY_PAD_S) & (ts <= ts[b] + REPLAY_PAD_S)
    return out


def register_frames(
    frames: Iterable[tuple[int, float, np.ndarray]], reference: np.ndarray, venue, fps: float
) -> Registration:
    """Привязка кадров (номер, время, кадр BGR) к эталонному кадру. Кадры и эталон — одного размера."""
    height, width = reference.shape[:2]
    scale = min(1.0, WORK_WIDTH / width)
    work = (int(round(height * scale)), int(round(width * scale)))
    matcher = _Matcher(overlay_mask(work, venue.overlay))

    def to_work(image):
        return cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (work[1], work[0]), interpolation=cv2.INTER_AREA)

    reference_feat = matcher.features(to_work(reference))
    sequence = _Sequence(matcher, work, fps)
    badge, badge_xy = venue.replay_badge, venue.replay_badge_xy
    records: list[_Frame] = []
    replay_hits = []
    started = time.perf_counter()
    for frame_id, ts, image in frames:
        if image.shape[:2] != (height, width):
            raise ValueError('Кадр записи и эталонный кадр профиля разного размера')
        gray_full = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if badge is not None else None
        hit = badge is not None and _replay_score(gray_full, badge, badge_xy) >= REPLAY_SCORE
        replay_hits.append(hit)
        frame = _Frame(int(frame_id), float(ts), replay=hit)
        records.append(sequence.step(frame, matcher.features(to_work(image))))
        if len(records) % 3000 == 0:
            elapsed = time.perf_counter() - started
            print(
                f'  привязка: {ts / 60:.1f} мин видео, опорных {len(sequence.keys)}, '
                f'{len(records) / elapsed:.1f} кадр/с',
                file=sys.stderr,
            )
    if not records:
        raise ValueError('В записи нет кадров для привязки')
    poses, summary = _adjust(sequence.keys, reference_feat, matcher)
    ts = np.array([r.ts for r in records])
    replay = replay_flags(ts, np.array(replay_hits))
    S = np.diag([scale, scale, 1.0])
    S_inv = np.linalg.inv(S)
    rows = []
    for record, is_replay in zip(records, replay):
        H = None
        if record.H is not None and record.key in poses:
            key = sequence.keys[record.key]
            H = S_inv @ poses[record.key] @ np.linalg.inv(key.H) @ record.H @ S
            H = H / H[2, 2]
        if is_replay:
            status = 'replay'
        elif H is None:
            status = 'lost'
        elif record.src == 'key':
            status = 'ok'
        else:
            status = 'weak'
        values = H.ravel() if H is not None else np.full(9, np.nan)
        rows.append((record.frame_id, record.ts, status, record.key, record.inliers, *values.tolist()))
    data = pl.DataFrame(rows, schema=schemas.REGISTRATION, orient='row')
    counts = data.group_by('status').len()
    share = {s: 0.0 for s in STATUSES}
    for status, n in counts.iter_rows():
        share[status] = round(n / data.height, 4)
    summary.update(
        frames=data.height,
        share=share,
        replays=_intervals(ts, replay),
        seconds=round(time.perf_counter() - started, 1),
    )
    return Registration(data, summary)


def _intervals(ts: np.ndarray, flags: np.ndarray) -> list[list[float]]:
    """Интервалы [начало, конец] подряд идущих отмеченных кадров, в секундах."""
    flags = np.asarray(flags, bool)
    edges = np.flatnonzero(np.diff(np.concatenate([[False], flags, [False]]).astype(int)))
    return [[round(float(ts[a]), 2), round(float(ts[b - 1]), 2)] for a, b in zip(edges[::2], edges[1::2])]


def register_video(
    video: Path, venue, reference: np.ndarray, *, start_ms: int = 0, end_ms: int | None = None
) -> Registration:
    """Привязка кадров записи с частотой обработки (те же номера кадров, что у детекции)."""
    from aifootball.perception.frames import iter_frames

    frames = iter_frames(
        Path(video),
        venue.target_fps,
        expected_width=reference.shape[1],
        expected_height=reference.shape[0],
        start_ms=start_ms,
        end_ms=end_ms,
        seek=False,  # номера кадров — как у прохода детекции от начала записи
    )
    return register_frames(frames, reference, venue, venue.target_fps)


def frame_homographies(registration: pl.DataFrame, statuses=('ok',)) -> dict[int, np.ndarray]:
    """{номер кадра: гомография пикселей кадра -> пиксели эталона} для кадров с данными статусами."""
    usable = registration.filter(pl.col('status').is_in(list(statuses)))
    values = usable.select([f'h{i}' for i in range(9)]).to_numpy()
    return {int(f): values[n].reshape(3, 3) for n, f in enumerate(usable['frame_id'].to_list())}


def boxes_to_reference(boxes: np.ndarray, H: np.ndarray) -> np.ndarray:
    """Рамки x1, y1, x2, y2 кадра -> охватывающие рамки в пикселях эталона."""
    boxes = np.asarray(boxes, np.float64).reshape(-1, 4)
    if not len(boxes):
        return boxes
    corners = np.stack([boxes[:, [0, 1]], boxes[:, [2, 1]], boxes[:, [2, 3]], boxes[:, [0, 3]]], axis=1).reshape(-1, 2)
    moved = _apply(H, corners).reshape(-1, 4, 2)
    return np.column_stack([moved[..., 0].min(1), moved[..., 1].min(1), moved[..., 0].max(1), moved[..., 1].max(1)])


def detections_to_reference(
    detections: pl.DataFrame, registration: pl.DataFrame, overlay=(), frame_size: tuple[int, int] | None = None
) -> pl.DataFrame:
    """Детекции в пикселях эталона. Выпадают кадры без надёжной привязки и повторы, а также рамки,
    центр которых на графике трансляции (overlay — доли кадра, frame_size — ширина и высота кадра)."""
    homographies = frame_homographies(registration)
    data = detections.filter(pl.col('frame_id').is_in(list(homographies)))
    if overlay and frame_size and not data.is_empty():
        w, h = frame_size
        cx, cy = (pl.col('x1') + pl.col('x2')) / 2 / w, (pl.col('y1') + pl.col('y2')) / 2 / h
        for x1, y1, x2, y2 in overlay:
            data = data.filter(~(cx.is_between(x1, x2) & cy.is_between(y1, y2)))
    if data.is_empty():
        return data
    boxes = data.select('x1', 'y1', 'x2', 'y2').to_numpy().astype(np.float64)
    out = np.empty_like(boxes)
    frame_ids = data['frame_id'].to_numpy()
    for frame_id in np.unique(frame_ids):
        rows = frame_ids == frame_id
        out[rows] = boxes_to_reference(boxes[rows], homographies[int(frame_id)])
    return data.with_columns(
        x1=pl.Series(out[:, 0], dtype=pl.Float32),
        y1=pl.Series(out[:, 1], dtype=pl.Float32),
        x2=pl.Series(out[:, 2], dtype=pl.Float32),
        y2=pl.Series(out[:, 3], dtype=pl.Float32),
    )


def registration_messages(summary: dict | None) -> tuple[list[str], list[str]]:
    """Предупреждения и критические ошибки проверок качества по итогам привязки поворотной камеры."""
    if not summary:
        return [], []
    share = summary['share']
    replays = summary.get('replays') or []
    replay_s = sum(b - a for a, b in replays)
    note = (
        f'Камера поворотная: к полю привязано {share["ok"]:.0%} кадров; '
        f'повторы ({len(replays)}, {replay_s:.0f} с) и кадры без привязки в координаты не вошли'
    )
    if share['ok'] < MIN_LINKED_SHARE:
        return [note], [
            f'К полю привязано лишь {share["ok"]:.0%} кадров: проверьте эталонный кадр профиля и графику трансляции'
        ]
    return [note], []
