import numpy as np

from aifootball.perception.ball_detect import (
    cover_tiles,
    detect_ball_in_frame,
    mask_outside_pitch,
    merge_tile_boxes,
    pitch_keep_mask,
)


def test_mask_outside_pitch_keeps_margin():
    frame = np.full((100, 200, 3), 200, np.uint8)
    polygon = np.array([[50, 20], [150, 20], [150, 80], [50, 80]], np.float32)

    masked = mask_outside_pitch(frame, polygon, margin_px=10)

    assert (masked[50, 100] == 200).all()  # поле
    assert (masked[50, 45] == 200).all()   # запас у линии
    assert (masked[50, 20] == 114).all()   # дальше запаса — закрашено серым
    assert (frame[50, 20] == 200).all()    # исходный кадр не тронут


def test_cover_tiles_cover_box_with_overlap():
    tiles = cover_tiles((48, 230, 2425, 1944), tile=1280, width=2592, height=1944)

    assert len(tiles) == 4
    covered = np.zeros((1944, 2592), bool)
    for x0, y0 in tiles:
        assert 0 <= x0 <= 2592 - 1280 and 0 <= y0 <= 1944 - 1280
        covered[y0:y0 + 1280, x0:x0 + 1280] = True
    assert covered[230:1944, 48:2425].all()


def test_cover_tiles_start_at_frame_edge_when_frame_is_smaller_than_tile():
    # Кадр 1280x720 и вырезка 1280: начало вырезки уходило в y = -560, срез брал только низ кадра,
    # а рамки мяча сдвигались на 560 px вверх — за поле — и отбрасывались. Мяч не находился вовсе.
    assert cover_tiles((0, 347, 1197, 719), tile=1280, width=1280, height=720) == [(0, 0)]
    assert cover_tiles((10, 20, 900, 1000), tile=1280, width=960, height=1080) == [(0, 0)]


def test_merge_tile_boxes_joins_same_ball_from_two_tiles():
    boxes = np.array([[100, 100, 120, 120], [101, 99, 121, 119], [500, 500, 520, 520]], float)
    confs = np.array([0.4, 0.9, 0.7])

    kept_boxes, kept_confs = merge_tile_boxes(boxes, confs)

    assert kept_confs.tolist() == [0.9, 0.7]
    np.testing.assert_allclose(kept_boxes[0], [101, 99, 121, 119])


def test_detect_ball_in_frame_masks_and_maps_back_to_frame():
    frame = np.full((400, 600, 3), 200, np.uint8)
    polygon = np.array([[100, 100], [500, 100], [500, 300], [100, 300]], np.float32)
    keep = pitch_keep_mask(frame.shape[:2], polygon, margin_px=10)
    tiles = [(0, 0), (300, 100)]
    seen = []

    def fake_predict(crops):
        seen.extend(crops)
        # во второй вырезке «мяч» в точке (50, 60) вырезки
        return [(np.zeros((0, 4)), np.zeros(0)), (np.array([[45.0, 55.0, 55.0, 65.0]]), np.array([0.8]))]

    boxes, confs = detect_ball_in_frame(frame, keep, tiles, tile=300, predict=fake_predict)

    np.testing.assert_allclose(boxes, [[345, 155, 355, 165]])
    assert confs.tolist() == [0.8]
    assert (seen[0][20, 20] == 114).all()   # за контуром — серая заливка, как при обучении
    assert (seen[0][150, 150] == 200).all()  # поле не тронуто
