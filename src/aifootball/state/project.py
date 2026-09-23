"""L2: tracks.parquet -> state.parquet (позиции на поле в метрах)."""

import polars as pl

from aifootball import schemas
from aifootball.geometry.homography import apply_homography
from aifootball.geometry.undistort import undistort_points
from aifootball.state.smooth import smooth_tracks
from aifootball.venue import Venue


def project_tracks(tracks: pl.DataFrame, venue: Venue) -> pl.DataFrame:
    """Берёт только точки на поле, переводит пиксели в метры и сглаживает."""
    H = venue.require_homography()
    on_pitch = tracks.filter(pl.col("in_pitch"))
    if on_pitch.is_empty():
        return schemas.empty("state")

    pixels = on_pitch.select("foot_x", "foot_y").to_numpy()
    meters = apply_homography(H, undistort_points(pixels, venue.calib))
    positions = on_pitch.select("frame_id", "ts", "track_id", "role", "team").with_columns(
        x_m=pl.Series(meters[:, 0]),
        y_m=pl.Series(meters[:, 1]),
    )
    return smooth_tracks(positions)
