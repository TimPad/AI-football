"""Главный инструмент отладки: исходный кадр и схема сверху, синхронно."""

from pathlib import Path

import cv2
import numpy as np
import polars as pl

from aifootball.perception.frames import iter_frames
from aifootball.venue import Venue
from aifootball.viz.overlay import TrackAnnotator, draw_tracks
from aifootball.viz.topdown import draw_pitch, draw_players


def render_debug_video(
    video: Path,
    tracks: pl.DataFrame,
    state: pl.DataFrame,
    venue: Venue,
    out_path: Path,
    max_seconds: float | None = None,
) -> int:
    """Пишет mp4 «кадр | вид сверху». Возвращает число записанных кадров."""
    tracks_groups = _by_frame_groups(tracks)
    state_groups = _by_frame_groups(state)
    pitch = draw_pitch(venue.length_m, venue.width_m)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    annotator = TrackAnnotator(trace_length=int(venue.target_fps * 3.0))

    writer = None
    written = 0
    try:
        for frame_id, ts, frame in iter_frames(video, venue.target_fps):
            if max_seconds is not None and ts > max_seconds:
                break
            left = annotator.annotate(frame, _get_frame_rows(tracks_groups, frame_id), venue.pitch_polygon_px)
            right = draw_players(pitch, _get_frame_rows(state_groups, frame_id), venue.width_m)
            right = _fit_height(right, left.shape[0])
            canvas = np.hstack([left, right])
            cv2.putText(
                canvas, f"t={ts:7.2f}s  frame={frame_id}", (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA,
            )
            if writer is None:
                height, width = canvas.shape[:2]
                writer = cv2.VideoWriter(
                    str(out_path), cv2.VideoWriter.fourcc(*"mp4v"), venue.target_fps, (width, height)
                )
            writer.write(canvas)
            written += 1
    finally:
        if writer is not None:
            writer.release()
    return written


def _by_frame_groups(df: pl.DataFrame) -> dict[int, pl.DataFrame]:
    if df.is_empty():
        return {}
    return {key[0]: group for key, group in df.partition_by("frame_id", as_dict=True).items()}


def _get_frame_rows(groups: dict[int, pl.DataFrame], frame_id: int) -> list[dict]:
    group = groups.get(frame_id)
    if group is None or len(group) == 0:
        return []
    return group.to_dicts()


def _fit_height(img: np.ndarray, height: int) -> np.ndarray:
    scale = height / img.shape[0]
    return cv2.resize(img, (int(round(img.shape[1] * scale)), height))
