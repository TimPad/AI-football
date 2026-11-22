"""Профиль поворотной камеры (трансляция с оператором): создание, плашка повтора, задание и process-job."""

import json
import sys
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import cv2
import numpy as np
import pytest
import yaml

from test_processor_ptz import BADGE_XY, REF_ORIGIN, H, W, badge_image, crop, origin, scene
from test_processor_resume import Predictor

from .test_analysis_import import upload as import_result
from .test_analysis_jobs import grant, new_job
from .test_analysis_queue import queue
from .test_camera_reference import upload
from .test_halls import camera_body, create_hall

OVERLAY = [[0.0, 0.0, 0.25, 0.1]]


def ptz_body(hall, **changes):
    """Поле 40 × 20 м на кадре 400 × 200 px эталона, 10 px = 1 м; контура нет."""
    body = camera_body(
        hall,
        name='Трансляция',
        frame_width=W,
        frame_height=H,
        motion='ptz',
        overlay=OVERLAY,
        points=[
            {'px': [0, 0], 'm': [0, 0]},
            {'px': [390, 0], 'm': [39, 0]},
            {'px': [390, 190], 'm': [39, 19]},
            {'px': [0, 190], 'm': [0, 19]},
            {'px': [200, 100], 'm': [20, 10]},
        ],
    )
    body.pop('pitch_polygon_px')
    return {**body, **changes}


def png(image):
    return cv2.imencode('.png', image)[1].tobytes()


def badge_frame():
    """Кадр повтора: эталонный вид с плашкой."""
    frame = crop(scene(), *REF_ORIGIN)
    badge = badge_image()
    x, y = BADGE_XY
    frame[y : y + badge.shape[0], x : x + badge.shape[1]] = badge[..., None]
    return frame


def put_badge(client, hall_id, profile_id, raw, x=BADGE_XY[0], y=BADGE_XY[1], width=40, height=24):
    return client.put(
        f'/api/v1/halls/{hall_id}/camera-profiles/{profile_id}/replay-badge',
        files={'file': ('replay.png', raw, 'image/png')},
        data={'x': str(x), 'y': str(y), 'width': str(width), 'height': str(height)},
    )


@pytest.fixture
def ptz_match(admin_client, match_factory):
    grant(admin_client)
    hall = create_hall(admin_client, pitch_length_m=40, pitch_width_m=20)
    r = admin_client.post(f'/api/v1/halls/{hall["id"]}/camera-profiles', json=ptz_body(hall))
    assert r.status_code == 201, r.text
    profile = r.json()
    return hall, profile, match_factory(hall_id=hall['id'], camera_profile_id=profile['id'])


def package(client, match, job):
    raw = client.get(f'/api/v1/matches/{match["id"]}/analysis/jobs/{job["id"]}/package')
    assert raw.status_code == 200, raw.text
    with ZipFile(BytesIO(raw.content)) as archive:
        return raw.content, {n: archive.read(n) for n in archive.namelist()}


def test_ptz_profile_has_no_outline_and_checks_its_fields(admin_client):
    hall = create_hall(admin_client, pitch_length_m=40, pitch_width_m=20)
    url = f'/api/v1/halls/{hall["id"]}/camera-profiles'
    created = admin_client.post(url, json=ptz_body(hall))
    assert created.status_code == 201, created.text
    profile = created.json()
    assert profile['motion'] == 'ptz' and profile['pitch_polygon_px'] is None and profile['overlay'] == OVERLAY
    assert profile['replay_badge'] is None and profile['reprojection_error_m'] < 0.01
    listed = admin_client.get(url).json()['items']
    assert [p['motion'] for p in listed] == ['ptz']
    without_overlay = admin_client.post(url, json=ptz_body(hall, overlay=None)).json()
    assert without_overlay['overlay'] == [] and without_overlay['version'] == 2
    polygon = [[0, 0], [390, 0], [390, 190], [0, 190]]
    calibration = {'K': [[400, 0, 200], [0, 400, 100], [0, 0, 1]], 'dist': [0, 0, 0, 0]}
    for wrong in (
        {'pitch_polygon_px': polygon},  # контур поворотной камеры строится по гомографии
        {'calibration': calibration},  # зум меняет дисторсию
        {'overlay': [[0.5, 0, 0.2, 0.1]]},  # x1 > x2
        {'overlay': [[0, 0, 1.2, 0.1]]},  # за кадром
        {'motion': 'drone'},
    ):
        assert admin_client.post(url, json=ptz_body(hall, **wrong)).status_code == 422, wrong
    fixed = camera_body(hall, frame_width=W, frame_height=H, points=ptz_body(hall)['points'])
    assert admin_client.post(url, json={**fixed, 'overlay': OVERLAY}).status_code == 422
    assert admin_client.post(url, json={**fixed, 'pitch_polygon_px': None}).status_code == 422
    # Углы поля отмечены «восьмёркой»: горизонт гомографии проходит через поле, контур по ней не построить.
    corners = [([0, 0], [0, 0]), ([390, 0], [39, 0]), ([390, 190], [0, 19]), ([0, 190], [39, 19])]
    twisted = ptz_body(hall, points=[{'px': px, 'm': m} for px, m in corners])
    response = admin_client.post(url, json=twisted)
    assert response.status_code == 422 and response.json()['error']['code'] == 'camera_geometry', response.text


def test_fixed_profile_request_hash_is_unchanged(admin_client):
    """Повтор запроса неподвижной камеры, отправленного до поворотных профилей, не конфликтует."""
    from aifootball.service.halls.operations import digest
    from aifootball.service.halls.schemas import CameraCreate

    hall = create_hall(admin_client)
    body = camera_body(hall)
    data = CameraCreate(**body).model_dump(mode='json')
    legacy_fields = {'request_id', 'expected_hall_revision', 'name', 'frame_width', 'frame_height', 'points'}
    legacy_fields |= {'pitch_polygon_px', 'calibration'}  # поля запроса до поворотных профилей
    legacy = {k: v for k, v in data.items() if k in legacy_fields}
    hashed = sha256(json.dumps({'id': hall['id'], 'data': legacy}, sort_keys=True, separators=(',', ':')).encode())
    assert set(data) - legacy_fields == {'motion', 'overlay'}
    assert digest(CameraCreate(**body), hall['id']) == hashed.hexdigest()
    url = f'/api/v1/halls/{hall["id"]}/camera-profiles'
    first = admin_client.post(url, json=body).json()
    assert first['motion'] == 'fixed' and first['overlay'] is None
    assert admin_client.post(url, json={**body, 'motion': 'fixed'}).json() == first


def test_replay_badge_is_cut_from_a_full_frame_once(admin_client, ptz_match):
    hall, profile, _ = ptz_match
    raw = png(badge_frame())
    assert put_badge(admin_client, hall['id'], profile['id'], png(badge_frame()[:100])).status_code == 422
    for wrong in ({'x': 380}, {'width': 300}, {'width': 4}):  # за кадром, слишком велика, слишком мала
        response = put_badge(admin_client, hall['id'], profile['id'], raw, **wrong)
        assert response.status_code == 422, (wrong, response.text)
    flat = put_badge(admin_client, hall['id'], profile['id'], png(np.full((H, W, 3), 128, np.uint8)))
    assert flat.json()['error']['code'] == 'badge_area'
    saved = put_badge(admin_client, hall['id'], profile['id'], raw)
    assert saved.status_code == 200, saved.text
    badge = saved.json()['replay_badge']
    assert badge['xy'] == list(BADGE_XY) and badge['size'] == [40, 24]
    image = admin_client.get(f'/api/v1/halls/{hall["id"]}/camera-profiles/{profile["id"]}/replay-badge')
    assert image.headers['content-type'] == 'image/png' and sha256(image.content).hexdigest() == badge['sha256']
    cut = cv2.imdecode(np.frombuffer(image.content, np.uint8), cv2.IMREAD_GRAYSCALE)
    assert np.abs(cut.astype(int) - badge_image()).max() <= 1
    assert put_badge(admin_client, hall['id'], profile['id'], raw).json()['replay_badge'] == badge  # повтор
    assert put_badge(admin_client, hall['id'], profile['id'], raw, x=320).status_code == 409
    fixed_hall = create_hall(admin_client)
    fixed = admin_client.post(f'/api/v1/halls/{fixed_hall["id"]}/camera-profiles', json=camera_body(fixed_hall))
    response = put_badge(admin_client, fixed_hall['id'], fixed.json()['id'], raw)
    assert response.json()['error']['code'] == 'camera_motion'


def test_ptz_job_needs_reference_and_carries_camera_section(admin_client, ptz_match, tmp_path):
    from aifootball.processor.job import read_job

    hall, profile, match = ptz_match
    path = f'/api/v1/matches/{match["id"]}/analysis/jobs'
    refused = admin_client.post(path, json={'request_id': '00000000-0000-4000-8000-000000000001'})
    assert refused.status_code == 422 and refused.json()['error']['code'] == 'reference_required'
    reference = upload(admin_client, hall['id'], profile['id'], png(crop(scene(), *REF_ORIGIN)), 'r.png', 'image/png')
    assert reference.status_code == 200, reference.text
    job = new_job(admin_client, match)
    camera = job['context']['camera']
    assert camera['motion'] == 'ptz' and camera['overlay'] == OVERLAY and camera['polygon_px'] is None
    assert 'replay_badge' not in camera
    assert not queue(admin_client, match)['items'][0]['context_stale']  # SQL-снимок камеры в очереди совпал
    raw, files = package(admin_client, match, job)
    assert 'pitch_polygon.json' not in files and 'replay_badge.png' not in files and 'reference.jpg' in files
    assert yaml.safe_load(files['venue.yaml'])['camera'] == {'motion': 'ptz', 'overlay': OVERLAY}
    (tmp_path / 'job.zip').write_bytes(raw)
    assert read_job(tmp_path / 'job.zip').contract['context_hash'] == job['context_hash']

    assert put_badge(admin_client, hall['id'], profile['id'], png(badge_frame())).status_code == 200
    assert queue(admin_client, match)['items'][0]['context_stale']  # плашка меняет снимок камеры
    second = new_job(admin_client, match)
    badge = second['context']['camera']['replay_badge']
    assert not queue(admin_client, match)['items'][0]['context_stale']
    raw, files = package(admin_client, match, second)
    assert sha256(files['replay_badge.png']).hexdigest() == badge['sha256']
    assert yaml.safe_load(files['venue.yaml'])['camera']['replay_badge_xy'] == list(BADGE_XY)
    (tmp_path / 'job2.zip').write_bytes(raw)
    assert read_job(tmp_path / 'job2.zip').files['replay_badge.png'] == files['replay_badge.png']
    # Прежнее задание выдаётся как было: без плашки.
    assert 'replay_badge.png' not in package(admin_client, match, job)[1]
    config = admin_client.get(f'/api/v1/matches/{match["id"]}/cv-config')
    with ZipFile(BytesIO(config.content)) as archive:
        assert {'reference.jpg', 'replay_badge.png', 'venue.yaml'} <= set(archive.namelist())
        assert 'pitch_polygon.json' not in archive.namelist()


def test_fixed_profile_context_and_package_are_unchanged(admin_client, match_factory):
    grant(admin_client)
    hall = create_hall(admin_client)
    profile = admin_client.post(f'/api/v1/halls/{hall["id"]}/camera-profiles', json=camera_body(hall)).json()
    match = match_factory(hall_id=hall['id'], camera_profile_id=profile['id'])
    job = new_job(admin_client, match)
    assert set(job['context']['camera']) == {
        'id',
        'version',
        'frame_width',
        'frame_height',
        'homography',
        'polygon_px',
        'calibration',
    }
    _, files = package(admin_client, match, job)
    assert set(files) == {'job.json', 'venue.yaml', 'homography.json', 'pitch_polygon.json', 'source.json'}
    assert 'camera' not in yaml.safe_load(files['venue.yaml'])
    config = admin_client.get(f'/api/v1/matches/{match["id"]}/cv-config')
    with ZipFile(BytesIO(config.content)) as archive:
        assert archive.namelist() == ['venue.yaml', 'homography.json', 'pitch_polygon.json', 'source.json']


def test_ptz_job_from_cabinet_passes_process_job(admin_client, ptz_match, tmp_path, monkeypatch):
    """Готовность: задание поворотного профиля из кабинета обрабатывается process-job на синтетической
    трансляции (пан вокруг эталона, повтор с плашкой), а результат принимается тем же матчем."""
    from aifootball.analytics.exchange import validate_result
    from aifootball.processor.job import process_job

    hall, profile, match = ptz_match
    image = scene()
    upload(admin_client, hall['id'], profile['id'], png(crop(image, *REF_ORIGIN)), 'r.png', 'image/png')
    assert put_badge(admin_client, hall['id'], profile['id'], png(badge_frame())).status_code == 200
    job = new_job(admin_client, match)
    raw, _ = package(admin_client, match, job)
    (tmp_path / 'job.zip').write_bytes(raw)

    badge = badge_image()
    video = tmp_path / 'broadcast.mp4'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter.fourcc(*'mp4v'), 2, (W, H))
    for n in range(130):
        frame = crop(image, *origin(n))
        if 90 <= n < 102:
            x, y = BADGE_XY
            frame[y : y + badge.shape[0], x : x + badge.shape[1]] = badge[..., None]
        writer.write(frame)
    writer.release()
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(YOLO=Predictor))
    Predictor.calls, Predictor.empty = 0, False
    models = tmp_path / 'models'
    models.mkdir()
    (models / 'yolo11m.pt').write_bytes(b'synthetic weights')

    output = process_job(tmp_path / 'job.zip', video, tmp_path / 'result.zip', models=models)
    result = validate_result(output)
    assert result.manifest['context_hash'] == job['context_hash']
    assert len(result.checks['camera_registration']['replays']) == 1
    assert result.checks['camera_registration']['share']['ok'] > 0.85
    imported = import_result(admin_client, match, output.read_bytes())
    assert imported.status_code == 200, imported.text
    assert queue(admin_client, match)['items'][0]['status'] == 'review'
