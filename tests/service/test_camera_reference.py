"""Эталонный кадр профиля камеры: загрузка, неизменность, контекст задания и кадр в job.zip."""
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile
import json
import pytest
from PIL import Image
from .test_analysis_jobs import analytics_match, new_job, grant  # noqa: F401
from .test_halls import create_hall, camera_body


def frame(size=(1000, 500), color=(40, 90, 160), fmt='JPEG'):
    out = BytesIO(); Image.new('RGB', size, color).save(out, format=fmt); return out.getvalue()


def upload(client, hall_id, profile_id, raw, name='frame.jpg', mime='image/jpeg'):
    return client.put(f'/api/v1/halls/{hall_id}/camera-profiles/{profile_id}/reference-frame', files={'file': (name, raw, mime)})


def camera(client):
    hall = create_hall(client)
    profile = client.post(f"/api/v1/halls/{hall['id']}/camera-profiles", json=camera_body(hall))
    assert profile.status_code == 201, profile.text
    return hall, profile.json()


def test_reference_is_checked_set_once_and_downloadable(admin_client):
    hall, profile = camera(admin_client)
    assert profile['reference_sha256'] is None
    assert upload(admin_client, hall['id'], profile['id'], frame((640, 480))).json()['error']['code'] == 'image_size'
    assert upload(admin_client, hall['id'], profile['id'], b'not an image').json()['error']['code'] == 'file_type'
    assert upload(admin_client, hall['id'], profile['id'], frame(fmt='PNG'), 'f.png', 'image/jpeg').status_code == 422
    first = upload(admin_client, hall['id'], profile['id'], frame(fmt='PNG'), 'f.png', 'image/png')
    assert first.status_code == 200, first.text
    digest = first.json()['reference_sha256']
    # Повтор того же кадра — тот же результат; другой кадр для той же версии — конфликт
    assert upload(admin_client, hall['id'], profile['id'], frame(fmt='PNG'), 'f.png', 'image/png').json()['reference_sha256'] == digest
    assert upload(admin_client, hall['id'], profile['id'], frame(color=(0, 0, 0))).status_code == 409
    image = admin_client.get(f"/api/v1/halls/{hall['id']}/camera-profiles/{profile['id']}/reference-frame")
    assert image.status_code == 200 and image.headers['content-type'] == 'image/jpeg'
    assert sha256(image.content).hexdigest() == digest and b'Exif' not in image.content[:200]
    other = create_hall(admin_client)
    assert admin_client.get(f"/api/v1/halls/{other['id']}/camera-profiles/{profile['id']}/reference-frame").status_code == 404


def test_job_carries_the_reference_only_when_set(admin_client, analytics_match, tmp_path):
    before = new_job(admin_client, analytics_match)
    assert 'reference_sha256' not in before['context']['camera']   # контекст и задания без кадра не меняются
    hall_id, profile_id = analytics_match['hall_id'], analytics_match['camera_profile_id']
    digest = upload(admin_client, hall_id, profile_id, frame()).json()['reference_sha256']
    job = new_job(admin_client, analytics_match)
    assert job['context']['camera']['reference_sha256'] == digest and job['context_hash'] != before['context_hash']
    raw = admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis/jobs/{job['id']}/package")
    assert raw.status_code == 200, raw.text
    with ZipFile(BytesIO(raw.content)) as archive:
        assert sha256(archive.read('reference.jpg')).hexdigest() == digest
        assert json.loads(archive.read('job.json'))['context']['camera']['reference_sha256'] == digest
    # Обработчик принимает такое задание: хэш кадра сходится с контекстом
    from aifootball.processor.job import read_job
    (tmp_path / 'job.zip').write_bytes(raw.content)
    assert read_job(tmp_path / 'job.zip').files['reference.jpg'] == admin_client.get(
        f"/api/v1/halls/{hall_id}/camera-profiles/{profile_id}/reference-frame").content
    old = admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis/jobs/{before['id']}/package")
    with ZipFile(BytesIO(old.content)) as archive:
        assert 'reference.jpg' not in archive.namelist()
