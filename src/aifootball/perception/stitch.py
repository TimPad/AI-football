"""L1: сшивка оборванных треков на основе цвета и кинематической близости."""

import numpy as np
import polars as pl

# Смена игрока внутри трека: цвет торса много кадров подряд на стороне другой команды.
# Сторона — проекция цвета (a, b) на отрезок между цветами команд: 0 — A, 1 — B. Сырое расстояние
# между цветами не годится: оранжевая форма от света гуляет сильнее, чем шум между кадрами.
SPLIT_SIDE_MARGIN = 0.2  # проекция в 0.3..0.7 — цвет неясный, кадр не голосует
SPLIT_MIN_FRAMES = 8  # ~0.5 с при 15 fps: короче — блик, наклон, рука соседа
SPLIT_REF_FRAMES = 15  # команда куска — большинство последних уверенных кадров


def split_on_color_change(
    tracks: pl.DataFrame,
    centers: np.ndarray | None,
    min_frames: int = SPLIT_MIN_FRAMES,
    margin: float = SPLIT_SIDE_MARGIN,
    ref_frames: int = SPLIT_REF_FRAMES,
) -> pl.DataFrame:
    """Разрезает трек там, где он перескочил на игрока другой команды.

    Когда игроки сходятся, ByteTrack по пересечению рамок может продолжить трек на
    сопернике, и тот уносит с собой команду трека. Признак — min_frames уверенных
    кадров подряд с цветом другой команды (centers — teams.team_color_centers).
    Кадры, где торс закрыт чужой рамкой, не голосуют: там цвет смешан, а трек
    обычно верный. Новый кусок получает новый track_id; соединить куски одного
    игрока обратно — дело stitch_tracks.
    """
    if tracks.is_empty() or centers is None:
        return tracks

    df = tracks.with_row_index("_row")
    color_a, color_b = df["torso_a"].to_numpy(), df["torso_b"].to_numpy()
    axis = centers[1] - centers[0]
    along = ((color_a - centers[0][0]) * axis[0] + (color_b - centers[0][1]) * axis[1]) / float(axis @ axis)
    usable = df["in_pitch"].to_numpy() & ~np.isnan(color_a) & ~_torso_covered(df)
    side = np.where(usable & (along < 0.5 - margin), 0, np.where(usable & (along > 0.5 + margin), 1, -1))

    new_ids = df["track_id"].to_numpy().copy()
    next_id = int(new_ids.max()) + 1
    order = df.select("_row", "track_id", "frame_id").sort("track_id", "frame_id")
    for (_,), group in order.partition_by("track_id", as_dict=True, maintain_order=True).items():
        rows = group["_row"].to_numpy()
        segment_id = int(new_ids[rows[0]])
        recent: list[int] = []  # стороны последних уверенных кадров куска
        run: list[int] = []  # позиции (в rows) подряд идущих кадров чужой стороны
        for pos, row in enumerate(rows):
            new_ids[row] = segment_id
            if side[row] < 0:
                continue
            own = int(np.mean(recent[-ref_frames:]) > 0.5) if recent else side[row]
            if side[row] == own:
                run = []
                recent.append(int(side[row]))
                continue
            run.append(pos)
            if len(run) == min_frames:
                segment_id, next_id = next_id, next_id + 1
                new_ids[rows[run[0]:pos + 1]] = segment_id
                recent = [int(side[row])] * min_frames
                run = []

    return tracks.with_columns(track_id=pl.Series(new_ids, dtype=tracks.schema["track_id"]))


def _torso_covered(df: pl.DataFrame) -> np.ndarray:
    """Пересекается ли зона торса (как в color.torso_lab) с рамкой другого человека в том же кадре."""
    covered = np.zeros(df.height, dtype=bool)
    for group in df.select("_row", "x1", "y1", "x2", "y2", "frame_id").partition_by("frame_id"):
        if group.height < 2:
            continue
        x1, y1, x2, y2 = (group[c].to_numpy() for c in ("x1", "y1", "x2", "y2"))
        w, h = x2 - x1, y2 - y1
        tx1, tx2, ty1, ty2 = x1 + 0.3 * w, x1 + 0.7 * w, y1 + 0.2 * h, y1 + 0.5 * h
        overlap = (
            (np.minimum(tx2[:, None], x2[None, :]) > np.maximum(tx1[:, None], x1[None, :]))
            & (np.minimum(ty2[:, None], y2[None, :]) > np.maximum(ty1[:, None], y1[None, :]))
        )
        np.fill_diagonal(overlap, False)
        covered[group["_row"].to_numpy()] = overlap.any(axis=1)
    return covered


def stitch_tracks(
    tracks: pl.DataFrame,
    max_gap_s: float = 5.0,
    max_color_dist: float = 15.0,
    max_spatial_dist_px: float = 150.0,
) -> pl.DataFrame:
    """Объединяет разделенные треки одного и того же игрока.

    Использует зазор во времени, совпадение цвета формы (Lab) и близкие
    координаты конца первого и начала второго трека.
    """
    if tracks.is_empty():
        return tracks

    # Собираем метаданные по каждому треку
    valid = tracks.filter(pl.col("in_pitch") & pl.col("torso_a").is_not_nan())
    if valid.is_empty():
        return tracks

    stats = (
        valid.group_by("track_id")
        .agg(
            start_ts=pl.col("ts").min(),
            end_ts=pl.col("ts").max(),
            a=pl.col("torso_a").median(),
            b=pl.col("torso_b").median(),
        )
        .sort("start_ts")
    )

    if len(stats) < 2:
        return tracks

    # Находим точки начала и конца каждого трека из исходного tracks
    start_pos = (
        tracks.sort("ts")
        .group_by("track_id", maintain_order=True)
        .agg(
            start_x=pl.col("foot_x").first(),
            start_y=pl.col("foot_y").first(),
        )
    )
    end_pos = (
        tracks.sort("ts")
        .group_by("track_id", maintain_order=True)
        .agg(
            end_x=pl.col("foot_x").last(),
            end_y=pl.col("foot_y").last(),
        )
    )

    meta = (
        stats.join(start_pos, on="track_id", how="inner")
        .join(end_pos, on="track_id", how="inner")
        .to_dicts()
    )

    # Составляем список кандидатов на сшивку (T_A -> T_B)
    candidates = []
    for i in range(len(meta)):
        ta = meta[i]
        for j in range(i + 1, len(meta)):
            tb = meta[j]
            dt = tb["start_ts"] - ta["end_ts"]
            if dt <= 0:
                continue
            if dt > max_gap_s:
                break  # meta отсортирован по start_ts

            color_dist = float(np.hypot(ta["a"] - tb["a"], ta["b"] - tb["b"]))
            if color_dist > max_color_dist:
                continue

            spatial_dist = float(np.hypot(tb["start_x"] - ta["end_x"], tb["start_y"] - ta["end_y"]))
            if spatial_dist > max_spatial_dist_px:
                continue

            cost = color_dist + 0.1 * spatial_dist + 2.0 * dt
            candidates.append((cost, ta["track_id"], tb["track_id"]))

    if not candidates:
        return tracks

    # Жадный выбор пар с наименьшей стоимостью (Union-Find)
    candidates.sort(key=lambda x: x[0])
    parent = {}

    def find(i: int) -> int:
        if parent.setdefault(i, i) == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    used_left = set()
    used_right = set()

    for cost, tid_a, tid_b in candidates:
        root_a = find(tid_a)
        root_b = find(tid_b)
        if root_a != root_b and tid_a not in used_left and tid_b not in used_right:
            parent[root_b] = root_a
            used_left.add(tid_a)
            used_right.add(tid_b)

    # Применяем маппинг старых track_id на новые
    mapping = {tid: find(tid) for tid in parent}
    if not mapping:
        return tracks

    mapping_df = pl.DataFrame(
        {"track_id": list(mapping.keys()), "new_track_id": list(mapping.values())},
        schema={"track_id": pl.Int32, "new_track_id": pl.Int32},
    )

    return (
        tracks.join(mapping_df, on="track_id", how="left")
        .with_columns(
            track_id=pl.when(pl.col("new_track_id").is_not_null())
            .then(pl.col("new_track_id"))
            .otherwise(pl.col("track_id"))
        )
        .drop("new_track_id")
        .sort("frame_id", "track_id")
    )
