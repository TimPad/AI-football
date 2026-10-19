import numpy as np
import pytest

from aifootball import schemas
from aifootball.perception.frames import iter_frames
from aifootball.tools.ball_labels import (
    BallLabels,
    render_view,
    sampled_frame_ids,
    spread,
)
from conftest import write_video


def test_sampled_frame_ids_match_pipeline(tmp_path):
    # Размечать надо ровно те кадры, которые видит детектор, иначе сравнивать не с чем
    video = write_video(tmp_path / "v.mp4", n_frames=50, fps=25.0)

    expected = [frame_id for frame_id, _, _ in iter_frames(video, 10)]

    assert sampled_frame_ids(50, 25.0, 10) == expected


def test_spread_takes_evenly_spaced_frames():
    ids = list(range(0, 100, 2))

    picked = spread(ids, 5)

    assert picked == [0, 24, 48, 74, 98]
    assert spread(ids, 500) == ids


def test_labels_survive_restart(tmp_path):
    path = tmp_path / "gt" / "ball.parquet"
    labels = BallLabels(path, src_fps=25.0)
    labels.set(10, "visible", (100.5, 200.25))
    labels.set(20, "absent")

    again = BallLabels(path, src_fps=25.0)

    assert again.get(10) == {"status": "visible", "x": 100.5, "y": 200.25}
    assert again.get(20) == {"status": "absent", "x": None, "y": None}
    df = schemas.read(path, "ball_labels")
    assert df.sort("frame_id")["ts"].to_list() == [0.4, 0.8]


def test_relabel_overwrites(tmp_path):
    labels = BallLabels(tmp_path / "ball.parquet", src_fps=25.0)
    labels.set(10, "visible", (1.0, 2.0))

    labels.set(10, "hidden")

    assert labels.get(10)["status"] == "hidden"
    assert len(schemas.read(tmp_path / "ball.parquet", "ball_labels")) == 1


@pytest.mark.parametrize("status, point", [("visible", None), ("absent", (1.0, 2.0)), ("ball", None)])
def test_inconsistent_label_rejected(tmp_path, status, point):
    labels = BallLabels(tmp_path / "ball.parquet", src_fps=25.0)

    with pytest.raises(ValueError):
        labels.set(10, status, point)


def test_resume_from_first_unlabeled(tmp_path):
    labels = BallLabels(tmp_path / "ball.parquet", src_fps=25.0)
    labels.set(0, "absent")
    labels.set(5, "hidden")

    assert labels.first_unlabeled([0, 5, 8, 10]) == 2
    assert labels.first_unlabeled([0, 5]) == 2  # всё размечено — за концом списка


def test_counts(tmp_path):
    labels = BallLabels(tmp_path / "ball.parquet", src_fps=25.0)
    labels.set(0, "visible", (1.0, 1.0))
    labels.set(3, "visible", (2.0, 2.0))
    labels.set(5, "absent")

    assert labels.counts() == {"visible": 2, "absent": 1, "hidden": 0}


def test_render_view_keeps_frame_size_and_marks_label():
    frame = np.full((720, 1280, 3), 90, np.uint8)

    shown = render_view(frame, scale=1.0, label={"status": "visible", "x": 640.0, "y": 500.0},
                        cursor=(640, 500), header="1/200")

    assert shown.shape == (720, 1280, 3)
    assert not np.array_equal(shown, frame)


@pytest.mark.parametrize("cursor", [(-40, 300), (300, -40), (1400, 300), (300, 900), (-40, -40)])
def test_render_view_survives_cursor_outside_frame(cursor):
    # На macOS окно OpenCV сообщает курсор и за своим краем: точка у края кадра (ближние ворота)
    # роняла разметку поля вместе со всеми поставленными точками.
    frame = np.full((720, 1280, 3), 90, np.uint8)

    shown = render_view(frame, scale=1.0, label=None, cursor=cursor, header="14/17")

    assert shown.shape == (720, 1280, 3)
