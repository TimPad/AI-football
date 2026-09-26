import cv2
import numpy as np
import polars as pl
import pytest
import yaml

from aifootball import schemas
from aifootball.tools.ball_dataset import (
    ball_diameter_px,
    cover_tiles,
    crop_around,
    crop_away_from,
    export_dataset,
    fit_person_height,
    mask_outside_pitch,
    time_blocks_split,
    yolo_label,
)
from conftest import make_venue_dir, write_video


def _persons(feet, heights):
    n = len(feet)
    return pl.DataFrame({
        "frame_id": list(range(n)),
        "ts": [0.0] * n,
        "cls": ["person"] * n,
        "x1": [f[0] - 10 for f in feet],
        "y1": [f[1] - h for f, h in zip(feet, heights)],
        "x2": [f[0] + 10 for f in feet],
        "y2": [f[1] for f in feet],
        "conf": [0.9] * n,
        "torso_l": [0.0] * n,
        "torso_a": [0.0] * n,
        "torso_b": [0.0] * n,
    }, schema=schemas.DETECTIONS)


def test_person_height_follows_position_and_ignores_outliers():
    # рост в кадре растёт к низу кадра: h = 40 + 0.1 * y; двое «сидят» — вдвое ниже
    rng = np.random.default_rng(0)
    feet = [(float(x), float(y)) for x, y in rng.uniform([0, 100], [1000, 900], (200, 2))]
    heights = [40 + 0.1 * y for _, y in feet]
    heights[0] /= 2
    heights[1] /= 2
    coef = fit_person_height(_persons(feet, heights))

    assert ball_diameter_px(coef, np.array([500.0]), np.array([500.0]))[0] == pytest.approx(90 / 6.7, rel=0.02)
    assert ball_diameter_px(coef, np.array([100.0]), np.array([900.0]))[0] == pytest.approx(130 / 6.7, rel=0.02)


def test_mask_outside_pitch_keeps_margin():
    frame = np.full((100, 200, 3), 200, np.uint8)
    polygon = np.array([[50, 20], [150, 20], [150, 80], [50, 80]], np.float32)

    masked = mask_outside_pitch(frame, polygon, margin_px=10)

    assert (masked[50, 100] == 200).all()  # поле
    assert (masked[50, 45] == 200).all()   # запас у линии
    assert (masked[50, 20] == 114).all()   # дальше запаса — закрашено серым
    assert (frame[50, 20] == 200).all()    # исходный кадр не тронут


def test_yolo_label_normalized_and_clipped():
    assert yolo_label(100.0, 50.0, 20.0, width=200, height=100) == "0 0.500000 0.500000 0.100000 0.200000"
    # мяч у края кадра: бокс обрезается по кадру, центр сдвигается внутрь
    assert yolo_label(5.0, 50.0, 20.0, width=200, height=100) == "0 0.037500 0.500000 0.075000 0.200000"


def test_time_blocks_split_keeps_neighbours_together():
    ids = list(range(0, 1000, 10))  # 100 кадров

    train, val = time_blocks_split(ids, val_fraction=0.2, blocks=10)

    assert sorted(train + val) == ids
    assert len(val) == 20
    # проверочные кадры идут целыми блоками по 10, а не вперемешку с обучающими
    runs = np.split(np.array(val), np.where(np.diff(val) != 10)[0] + 1)
    assert all(len(r) == 10 for r in runs)


def test_export_dataset_writes_yolo_layout(tmp_path):
    video = write_video(tmp_path / "v.mp4", n_frames=40, fps=10.0, size=(320, 240))
    venue = make_venue_dir(tmp_path / "venue", polygon=[[20, 20], [300, 20], [300, 220], [20, 220]])
    labels = pl.DataFrame({
        "frame_id": [0, 10, 20, 30],
        "ts": [0.0, 1.0, 2.0, 3.0],
        "status": ["visible", "absent", "hidden", "visible"],
        "x": [100.0, None, None, 160.0],
        "y": [120.0, None, None, 100.0],
    }, schema=schemas.BALL_LABELS)
    persons = _persons([(160.0, 200.0), (100.0, 60.0), (250.0, 150.0)], [67.0, 67.0, 67.0])

    info = export_dataset(video, venue, labels, persons, tmp_path / "ds", val_fraction=0.5, blocks=2, margin_px=10)

    assert info["skipped_hidden"] == 1
    images = sorted(p.name for p in (tmp_path / "ds" / "images").rglob("*.jpg"))
    assert images == ["f000000.jpg", "f000010.jpg", "f000030.jpg"]
    label = (tmp_path / "ds" / "labels" / "train" / "f000000.txt").read_text().split()
    assert label[0] == "0" and float(label[3]) == pytest.approx(10 / 320, rel=0.05)  # мяч ~67/6.7 = 10 px
    assert (tmp_path / "ds" / "labels" / "train" / "f000010.txt").read_text() == ""  # мяча нет — пустой пример
    data = yaml.safe_load((tmp_path / "ds" / "data.yaml").read_text())
    assert data["names"] == {0: "ball"}


def test_export_skips_ball_in_masked_area(tmp_path):
    # мяч у скамейки дальше запаса: на картинке там серая заливка — такой пример учит искать мяч на сером
    video = write_video(tmp_path / "v.mp4", n_frames=20, fps=10.0, size=(320, 240))
    venue = make_venue_dir(tmp_path / "venue", polygon=[[100, 20], [300, 20], [300, 220], [100, 220]])
    labels = pl.DataFrame({
        "frame_id": [0, 10], "ts": [0.0, 1.0], "status": ["visible", "visible"],
        "x": [200.0, 30.0], "y": [120.0, 120.0],
    }, schema=schemas.BALL_LABELS)
    persons = _persons([(200.0, 200.0)], [67.0])

    info = export_dataset(video, venue, labels, persons, tmp_path / "ds", val_fraction=0.5, blocks=2, margin_px=10)

    assert info["skipped_outside"] == 1
    assert sorted(p.name for p in (tmp_path / "ds" / "images").rglob("*.jpg")) == ["f000000.jpg"]


def test_crop_around_keeps_ball_inside_and_frame_bounds():
    for seed in range(50):
        x0, y0 = crop_around(1000.0, 30.0, tile=640, width=2592, height=1944, edge_px=40, seed=seed)
        assert 0 <= x0 <= 2592 - 640 and 0 <= y0 <= 1944 - 640
        assert x0 + 40 <= 1000 <= x0 + 640 - 40
        assert y0 <= 30 <= y0 + 640  # у края кадра мяч может быть ближе к краю вырезки — кадр кончается
    assert crop_around(1000.0, 900.0, 640, 2592, 1944, 40, seed=7) == crop_around(1000.0, 900.0, 640, 2592, 1944, 40, seed=7)


def test_crop_away_from_misses_ball():
    keep = np.full((1944, 2592), 255, np.uint8)
    for seed in range(50):
        x0, y0 = crop_away_from(1000.0, 900.0, keep, tile=640, seed=seed)
        assert not (x0 - 20 <= 1000 <= x0 + 640 + 20 and y0 - 20 <= 900 <= y0 + 640 + 20)


def test_crop_away_from_prefers_pitch():
    keep = np.zeros((1944, 2592), np.uint8)
    keep[1000:, :] = 255  # поле — нижняя половина кадра
    x0, y0 = crop_away_from(None, None, keep, tile=640, seed=1)
    assert (keep[y0:y0 + 640, x0:x0 + 640] > 0).mean() >= 0.5


def test_cover_tiles_cover_box_with_overlap():
    tiles = cover_tiles((48, 230, 2425, 1944), tile=1280, width=2592, height=1944)

    assert len(tiles) == 4
    covered = np.zeros((1944, 2592), bool)
    for x0, y0 in tiles:
        assert 0 <= x0 <= 2592 - 1280 and 0 <= y0 <= 1944 - 1280
        covered[y0:y0 + 1280, x0:x0 + 1280] = True
    assert covered[230:1944, 48:2425].all()


def test_export_tiles(tmp_path):
    video = write_video(tmp_path / "v.mp4", n_frames=20, fps=10.0, size=(320, 240))
    venue = make_venue_dir(tmp_path / "venue", polygon=[[20, 20], [300, 20], [300, 220], [20, 220]])
    labels = pl.DataFrame({
        "frame_id": [0, 10], "ts": [0.0, 1.0], "status": ["visible", "absent"],
        "x": [100.0, None], "y": [120.0, None],
    }, schema=schemas.BALL_LABELS)
    persons = _persons([(160.0, 200.0)], [67.0])

    export_dataset(video, venue, labels, persons, tmp_path / "ds", val_fraction=0.5, blocks=2, margin_px=10, tile=128)

    names = sorted(p.name for p in (tmp_path / "ds" / "images").rglob("*.jpg"))
    assert names == ["f000000_b.jpg", "f000000_n.jpg", "f000010_n.jpg"]
    img = next((tmp_path / "ds" / "images").rglob("f000000_b.jpg"))
    assert cv2.imread(str(img)).shape == (128, 128, 3)
    line = next((tmp_path / "ds" / "labels").rglob("f000000_b.txt")).read_text().split()
    assert float(line[3]) == pytest.approx(10 / 128, rel=0.05)  # размер мяча в пикселях сохранён
    assert next((tmp_path / "ds" / "labels").rglob("f000000_n.txt")).read_text() == ""


def test_yolo_label_min_box():
    # мелкий мяч размечаем боксом не меньше min_px: центр тот же, а модели есть на чём учиться
    assert yolo_label(100.0, 50.0, 10.0, width=200, height=100, min_px=32.0) == "0 0.500000 0.500000 0.160000 0.320000"
    assert yolo_label(100.0, 50.0, 40.0, width=200, height=100, min_px=32.0) == "0 0.500000 0.500000 0.200000 0.400000"
