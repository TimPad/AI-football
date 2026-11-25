import numpy as np

from aifootball.perception.ball_detect import (
    PTZ_FAR_M,
    PTZ_HORIZON,
    PtzBallDetector,
    clip_halfplane,
    cover_tiles,
    detect_ball_in_frame,
    frame_keep_mask,
    mask_outside_pitch,
    merge_tile_boxes,
    pitch_keep_mask,
    ptz_search_region_m,
)

# Камера у бровки смотрит вдоль поля: низ кадра — ближняя сторона (Y ≈ −2 м), верх — дальняя (Y ≈ 58 м).
# Точки плоскости с Y < −17 м — позади камеры: в кадр они проецируются «перевёрнутыми».
PTZ_SHAPE = (120, 200)
ALONG = np.array([[0.1, 0.0, -10.0], [0.0, -0.1 - 2 / 150, 11.6], [0.0, 1 / 150, 0.2]])  # пиксели кадра -> метры


def _expected_keep(frame_to_m, region, shape):
    """Пиксели, точка поля которых внутри зоны и не у «горизонта» камеры, — прямым перебором."""
    h, w = shape
    ys, xs = np.mgrid[0:h, 0:w]
    p = frame_to_m @ np.stack([xs.ravel(), ys.ravel(), np.ones(xs.size)])
    x_m, y_m = p[0] / p[2], p[1] / p[2]
    c = frame_to_m @ [w / 2, h / 2, 1.0]
    depth = 1 / p[2]  # глубина пикселя относительно его точки на плоскости
    inside = (
        (x_m >= region[:, 0].min())
        & (x_m <= region[:, 0].max())
        & (y_m >= region[:, 1].min())
        & (y_m <= region[:, 1].max())
        & (np.sign(depth) * np.sign(1 / c[2]) > 0)
        & (np.abs(depth) >= PTZ_HORIZON * abs(1 / c[2]))
    )
    return inside.reshape(h, w)


def test_mask_outside_pitch_keeps_margin():
    frame = np.full((100, 200, 3), 200, np.uint8)
    polygon = np.array([[50, 20], [150, 20], [150, 80], [50, 80]], np.float32)

    masked = mask_outside_pitch(frame, polygon, margin_px=10)

    assert (masked[50, 100] == 200).all()  # поле
    assert (masked[50, 45] == 200).all()  # запас у линии
    assert (masked[50, 20] == 114).all()  # дальше запаса — закрашено серым
    assert (frame[50, 20] == 200).all()  # исходный кадр не тронут


def test_cover_tiles_cover_box_with_overlap():
    tiles = cover_tiles((48, 230, 2425, 1944), tile=1280, width=2592, height=1944)

    assert len(tiles) == 4
    covered = np.zeros((1944, 2592), bool)
    for x0, y0 in tiles:
        assert 0 <= x0 <= 2592 - 1280 and 0 <= y0 <= 1944 - 1280
        covered[y0 : y0 + 1280, x0 : x0 + 1280] = True
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
    assert (seen[0][20, 20] == 114).all()  # за контуром — серая заливка, как при обучении
    assert (seen[0][150, 150] == 200).all()  # поле не тронуто


def test_clip_halfplane_keeps_the_side_where_g_is_not_negative():
    square = np.array([[0, 0], [2, 0], [2, 2], [0, 2]], float)

    half = clip_halfplane(square, lambda q: 1.0 - q[0])  # x <= 1

    assert sorted(map(tuple, half.round(6).tolist())) == [(0, 0), (0, 2), (1, 0), (1, 2)]
    assert len(clip_halfplane(square, lambda q: -1.0 - q[0])) == 0


def test_search_region_closes_only_the_side_nearest_to_the_camera():
    # Эталон 10 px на метр. Ближе к камере — низ эталона, где бы ни лежала ось y поля.
    down = np.array([[0.1, 0, 0], [0, 0.1, 0], [0, 0, 1.0]])  # y поля растёт вниз по кадру: ближняя линия y = 20
    region = ptz_search_region_m(down, 40, 20, near_margin_m=1.5)
    assert region.min(0).tolist() == [-PTZ_FAR_M, -PTZ_FAR_M]
    assert region.max(0).tolist() == [40 + PTZ_FAR_M, 21.5]

    up = np.array([[0.1, 0, 0], [0, -0.1, 20], [0, 0, 1.0]])  # y поля растёт вверх: ближняя линия y = 0
    region = ptz_search_region_m(up, 40, 20, near_margin_m=1.5)
    assert region.min(0).tolist() == [-PTZ_FAR_M, -1.5]
    assert region.max(0).tolist() == [40 + PTZ_FAR_M, 20 + PTZ_FAR_M]


def test_frame_mask_is_the_search_zone_seen_through_the_frame_homography():
    # Зона позади камеры (Y < −17 м): углы с Y = −60 проецируются «перевёрнутыми», и без обрезки по горизонту
    # многоугольник накрыл бы не ту часть кадра. Ближняя полоса (Y < −1.5) и дальняя (Y > 30) — закрыты.
    for region in (
        np.array([[-60, -60], [100, -60], [100, 30], [-60, 30]], float),
        np.array([[-60, -1.5], [100, -1.5], [100, 30], [-60, 30]], float),
    ):
        keep = frame_keep_mask(ALONG, region, PTZ_SHAPE) > 0
        expected = _expected_keep(ALONG, region, PTZ_SHAPE)

        assert 0.2 < expected.mean() < 0.95  # в кадре есть и зона поиска, и закрытая часть
        assert (keep != expected).sum() <= 2 * PTZ_SHAPE[1]  # расхождение — только пиксели на границах


def test_frame_mask_leaves_out_broadcast_graphics():
    region = np.array([[-60, -1.5], [100, -1.5], [100, 30], [-60, 30]], float)
    overlay_keep = np.full(PTZ_SHAPE, 255, np.uint8)
    overlay_keep[100:, 150:] = 0  # табло в правом нижнем углу

    keep = frame_keep_mask(ALONG, region, PTZ_SHAPE, overlay_keep)

    assert keep[110, 170] == 0 and keep[110, 100] == 255


def test_ptz_detector_skips_unregistered_frames_and_masks_each_frame_by_its_view():
    calls = []

    def fake_predict(crops):
        calls.append(crops)
        return [(np.array([[10.0, 10.0, 20.0, 20.0]]), np.array([0.9])) for _ in crops]

    top_down = np.array([[0.1, 0, 0], [0, 0.1, 0], [0, 0, 1.0]])  # кадр 200 x 120 px = 20 x 12 м
    region = np.array([[-60, -60], [100, -60], [100, 10], [-60, 10]], float)  # ближняя линия — y = 10 м
    detector = PtzBallDetector(
        fake_predict, {7: top_down}, region, PTZ_SHAPE, tile=1280, overlay=[(0.0, 0.0, 0.25, 0.25)]
    )
    frame = np.full((*PTZ_SHAPE, 3), 200, np.uint8)

    boxes, confs = detector(frame, 3)  # кадр без привязки: повтор, графика, потерянный вид
    assert boxes.shape == (0, 4) and not calls

    boxes, confs = detector(frame, 7)
    [[crop]] = calls
    np.testing.assert_allclose(boxes, [[10, 10, 20, 20]])
    assert confs.tolist() == [0.9]
    assert (crop[110, 100] == 114).all()  # дальше ближней линии — скамейки — закрашено
    assert (crop[5, 5] == 114).all()  # графика трансляции закрашена
    assert (crop[50, 100] == 200).all()  # поле не тронуто
