"""Поворотная камера: привязка кадров с паном и зумом к эталонному кадру, повторы, трекинг в плоскости эталона."""

import json

import cv2
import numpy as np
import polars as pl
import pytest
import yaml

from aifootball import schemas
from aifootball.geometry import registration as R
from aifootball.venue import load_venue

W, H = 640, 360
FPS = 10
SCENE_W, SCENE_H = 2600, 1000


def scene(seed=7):
    """«Зал» шире кадра: блоки разной яркости, круги и отрезки — особые точки для SIFT."""
    rng = np.random.default_rng(seed)
    image = cv2.resize(
        rng.integers(40, 215, (50, 130), dtype=np.uint8), (SCENE_W, SCENE_H), interpolation=cv2.INTER_NEAREST
    )
    for _ in range(900):
        center = tuple(int(v) for v in rng.integers(0, [SCENE_W, SCENE_H]))
        cv2.circle(image, center, int(rng.integers(3, 14)), int(rng.integers(0, 255)), -1)
    for _ in range(300):
        a = tuple(int(v) for v in rng.integers(0, [SCENE_W, SCENE_H]))
        b = (a[0] + int(rng.integers(-60, 60)), a[1] + int(rng.integers(-60, 60)))
        cv2.line(image, a, b, int(rng.integers(0, 255)), 2)
    return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)


def view(cx, cy, zoom, tilt=0.0):
    """Гомография «пиксели кадра -> пиксели сцены»: центр кадра смотрит в (cx, cy), зум и лёгкая перспектива."""
    s = 1.0 / zoom
    similarity = np.array([[s, 0, cx - s * W / 2], [0, s, cy - s * H / 2], [0, 0, 1.0]])
    perspective = np.array([[1, 0, 0], [0, 1, 0], [0, tilt, 1 - tilt * H / 2]])  # центр кадра остаётся на месте
    return similarity @ perspective


def render(image, V):
    return cv2.warpPerspective(image, V, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)


def grid_error(H_est, H_true):
    pts = np.array([[x, y] for x in np.linspace(20, W - 20, 9) for y in np.linspace(20, H - 20, 5)], np.float64)
    a = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), H_est).reshape(-1, 2)
    b = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), H_true).reshape(-1, 2)
    return float(np.hypot(*(a - b).T).max())


def ptz_venue(tmp_path, badge_xy=None, overlay=()):
    root = tmp_path / 'venue'
    root.mkdir()
    cfg = {
        'venue_id': 'ptz',
        'pitch': {'length_m': 40.0, 'width_m': 20.0},
        'processing': {
            'target_fps': FPS,
            'model': 'yolo11n.pt',
            'imgsz': 640,
            'conf_person': 0.25,
            'conf_ball': 0.25,
            'frame_width': W,
            'frame_height': H,
        },
        'camera': {'motion': 'ptz', 'overlay': [list(r) for r in overlay]},
    }
    if badge_xy is not None:
        cfg['camera']['replay_badge_xy'] = list(badge_xy)
    (root / 'venue.yaml').write_text(yaml.safe_dump(cfg), encoding='utf-8')
    (root / 'homography.json').write_text(json.dumps({'H': (METERS_FROM_SCENE @ REF_VIEW).tolist()}), encoding='utf-8')
    return root


REF_VIEW = view(1300, 500, 1.0)
# Поле 40 x 20 м лежит на сцене в x 100..2500, y 50..950.
METERS_FROM_SCENE = np.array([[40 / 2400, 0, -100 * 40 / 2400], [0, 20 / 900, -50 * 20 / 900], [0, 0, 1.0]])


def badge_image():
    image = np.zeros((40, 120, 3), np.uint8)
    cv2.putText(image, 'REPLAY', (6, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    return image


def pan_frames(image, path):
    """Пан с зумом, склейка на дальний вид (3.5 с), возврат панорамой, графика на весь экран, повтор с плашкой.

    Скорость пана — как у трансляции ВШЭ (~6–10 px кадра за кадр при 10 кадрах/с).
    Кадры: 0–79 пан, 80–114 склейка, 115–204 возврат, 205–209 графика, 210–224 игра, 225–244 повтор, 245–254 игра.
    """
    views = []
    for t in np.linspace(0, 1, 80):
        views.append(view(900 + 500 * t, 480 + 30 * np.sin(4 * t), 1.0 + 0.3 * np.sin(3 * t), 0.00005 * t))
    for _ in range(35):  # склейка: другой край сцены, без перекрытия с прежним видом
        views.append(view(2250, 520, 1.6))
    for t in np.linspace(0, 1, 90):  # оператор возвращается к центру
        views.append(view(2250 - 900 * t, 520 - 30 * t, 1.6 - 0.6 * t))
    noise = np.random.default_rng(3).integers(0, 255, (H, W, 3), dtype=np.uint8)
    frames = [render(image, V) for V in views]
    frames += [noise.copy() for _ in range(5)]  # графика на весь экран
    views += [None] * 5
    for t in np.linspace(0, 1, 15):
        V = view(1300 + 50 * t, 500, 1.0)
        frames.append(render(image, V))
        views.append(V)
    replay = []
    for t in np.linspace(0, 1, 20):  # повтор: та же камера, тот же зал — геометрия его не отличит
        V = view(900 + 300 * t, 500, 1.2)
        frame = render(image, V)
        frame[300:340, 500:620] = badge_image()
        replay.append((frame, V))
    frames += [f for f, _ in replay]
    views += [V for _, V in replay]
    for t in np.linspace(0, 1, 10):
        V = view(1200 + 100 * t, 500, 1.1)
        frames.append(render(image, V))
        views.append(V)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*'mp4v'), FPS, (W, H))
    for frame in frames:
        writer.write(frame)
    writer.release()
    return views


@pytest.fixture(scope='module')
def match(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('ptz')
    image = scene()
    root = ptz_venue(tmp, badge_xy=(500, 300), overlay=[(0.75, 0.8, 1.0, 1.0)])
    cv2.imwrite(str(root / 'replay_badge.png'), cv2.cvtColor(badge_image(), cv2.COLOR_BGR2GRAY))
    reference = render(image, REF_VIEW)
    views = pan_frames(image, tmp / 'pan.mp4')
    venue = load_venue(root)
    result = R.register_video(tmp / 'pan.mp4', venue, reference)
    return venue, views, result


def test_pan_and_zoom_frames_land_on_the_reference_plane(match):
    _, views, result = match
    data = result.frames
    assert data.height == len(views)
    homographies = R.frame_homographies(data)
    pan_px, meters = [], []
    to_meters = METERS_FROM_SCENE @ REF_VIEW
    for n, frame_id in enumerate(data['frame_id'].to_list()):
        if frame_id in homographies:
            H_est = homographies[frame_id]
            if n < 80:
                pan_px.append(grid_error(H_est, np.linalg.inv(REF_VIEW) @ views[n]))
            meters.append(grid_error(to_meters @ H_est, METERS_FROM_SCENE @ views[n]))
    # Привязаны все кадры, кроме ~3 с после склейки, графики и повтора.
    assert len(meters) >= 0.7 * len(views)
    # Пан от эталона: прямая сверка с опорными держит пиксель и не дрейфует, хотя кодек mp4v портит текстуру.
    assert len(pan_px) == 80 and np.median(pan_px) < 1.0 and max(pan_px) < 2.0
    # Дальний вид после склейки лежит в сотнях пикселей за краем эталона, и его положение собирается
    # цепочкой опорных: ошибка там несколько пикселей эталона и зависит от сборки OpenCV. В метрах поля
    # (1 px эталона = 1.7 см) это сантиметры.
    assert np.median(meters) < 0.03 and max(meters) < 0.15


def test_cut_to_unseen_view_starts_an_island_that_is_linked_back(match):
    _, views, result = match
    statuses = result.frames['status'].to_list()
    # После склейки вид не находится ~3 с, затем новый остров; возврат панорамой связывает его с эталоном.
    assert result.summary['islands'] >= 2
    assert result.summary['keyframes_linked_to_reference'] == result.summary['keyframes']
    cut = statuses[80:115]
    assert cut[:20].count('lost') >= 15 and cut[-3:] == ['ok'] * 3
    assert statuses[115:205].count('ok') >= 85


def test_full_screen_graphics_is_lost_and_replay_is_flagged(match):
    _, _, result = match
    statuses = result.frames['status'].to_list()
    assert statuses[205:210] == ['lost'] * 5
    assert statuses[210:220] == ['ok'] * 10
    # Повтор целиком, с запасом 0.5 с по краям: склейка бывает чуть раньше появления плашки.
    assert statuses[225:245] == ['replay'] * 20 and statuses[220:225] == ['replay'] * 5
    assert len(result.summary['replays']) == 1
    assert statuses[-5:] == ['ok'] * 5


def test_registration_round_trips_through_the_schema(match, tmp_path):
    _, _, result = match
    schemas.write(result.frames, tmp_path / 'registration.parquet', 'registration')
    back = schemas.read(tmp_path / 'registration.parquet', 'registration')
    assert back.equals(result.frames)


def test_ptz_venue_derives_the_pitch_polygon_from_the_homography(tmp_path):
    venue = load_venue(ptz_venue(tmp_path))
    meters = cv2.perspectiveTransform(venue.pitch_polygon_px.reshape(-1, 1, 2).astype(np.float64), venue.H).reshape(
        -1, 2
    )
    m = 0.3
    assert np.allclose(meters, [[-m, -m], [40 + m, -m], [40 + m, 20 + m], [-m, 20 + m]], atol=1e-3)


def test_ptz_venue_rejects_a_lens_model(tmp_path):
    root = ptz_venue(tmp_path)
    (root / 'calib.json').write_text('{"K": [[500, 0, 320], [0, 500, 180], [0, 0, 1]], "dist": [0, 0, 0, 0, 0]}')
    with pytest.raises(ValueError, match='calib'):
        load_venue(root)


def test_tracker_follows_a_player_while_the_camera_pans(tmp_path):
    """Игрок стоит, камера панорамирует: в пикселях кадра он «бежит», в плоскости эталона — на месте."""
    from aifootball.perception.track import track_people

    venue = load_venue(ptz_venue(tmp_path))
    rows, reg = [], []
    for n in range(30):
        V = view(1000 + 25 * n, 500, 1.0)  # 25 px сцены за кадр: рамки в кадре уезжают на 25 px
        to_ref = np.linalg.inv(REF_VIEW) @ V
        player_ref = np.array([[600.0, 200.0], [630.0, 270.0]])  # рамка игрока в пикселях эталона
        box = cv2.perspectiveTransform(player_ref.reshape(-1, 1, 2), np.linalg.inv(to_ref)).reshape(-1)
        other = box + [200, 0, 200, 0]
        for b in (box, other):
            rows.append((n, n / FPS, 'person', *b.tolist(), 0.9, 120.0, 150.0, 170.0))
        reg.append((n, n / FPS, 'ok', 0, 200, *to_ref.ravel().tolist()))
    detections = pl.DataFrame(rows, schema=schemas.DETECTIONS, orient='row')
    registration = pl.DataFrame(reg, schema=schemas.REGISTRATION, orient='row')
    tracks = track_people(detections, venue, registration)
    assert tracks['track_id'].n_unique() == 2
    first = tracks.filter(pl.col('track_id') == tracks['track_id'][0]).sort('frame_id')
    # Точка ног — в пикселях эталона и стоит на месте; рамки — исходные, в пикселях своего кадра.
    assert np.ptp(first['foot_x'].to_numpy()) < 1.0 and np.ptp(first['x1'].to_numpy()) > 500
    joined = first.join(detections.select('frame_id', 'x1'), on=['frame_id', 'x1'], how='inner')
    assert joined.height == first.height


def test_unregistered_frames_and_overlay_boxes_are_dropped():
    reg = pl.DataFrame(
        [(0, 0.0, 'ok', 0, 100, *np.eye(3).ravel()), (1, 0.1, 'replay', 0, 100, *np.eye(3).ravel())],
        schema=schemas.REGISTRATION,
        orient='row',
    )
    det = pl.DataFrame(
        [
            (0, 0.0, 'person', 10.0, 10.0, 20.0, 40.0, 0.9, 0.0, 0.0, 0.0),
            (0, 0.0, 'person', 600.0, 320.0, 620.0, 350.0, 0.9, 0.0, 0.0, 0.0),  # на графике в правом нижнем углу
            (1, 0.1, 'person', 10.0, 10.0, 20.0, 40.0, 0.9, 0.0, 0.0, 0.0),
        ],
        schema=schemas.DETECTIONS,
        orient='row',
    )
    out = R.detections_to_reference(det, reg, [(0.75, 0.8, 1.0, 1.0)], (W, H))
    assert out.height == 1 and out['frame_id'].to_list() == [0]


def test_replay_flags_bridge_flicker_and_pad_edges():
    ts = np.arange(0, 6, 0.1)
    hits = (ts >= 2) & (ts <= 4) & ~np.isclose(ts, 3.0)
    flags = R.replay_flags(ts, hits)
    assert flags[np.isclose(ts, 3.0)].all() and flags[np.isclose(ts, 1.5)].all() and not flags[ts < 1.45].any()
