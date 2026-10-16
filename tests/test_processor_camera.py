"""Эталонный кадр в задании: обработчик сверяет положение камеры до детекции."""
import json
from hashlib import sha256
from zipfile import ZipFile
import cv2
import numpy as np
import pytest
from test_processor_resume import cv_case, Predictor  # noqa: F401  (фикстура)


def textured(seed=3, size=(400, 200)):
    rng = np.random.default_rng(seed)
    image = cv2.resize(rng.integers(0, 255, (20, 40), dtype=np.uint8), size, interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)


def with_reference(path, image, sha=None):
    """Задание с эталонным кадром: хэш в контексте камеры, кадр — файлом reference.jpg."""
    with ZipFile(path) as source: files = {n: source.read(n) for n in source.namelist()}
    raw = cv2.imencode('.jpg', image)[1].tobytes()
    job = json.loads(files['job.json'])
    job['context']['camera']['reference_sha256'] = sha or sha256(raw).hexdigest()
    job['context_hash'] = sha256(json.dumps(job['context'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    files['job.json'] = json.dumps(job).encode(); files['reference.jpg'] = raw
    with ZipFile(path, 'w') as archive:
        for name, value in files.items(): archive.writestr(name, value)
    return path


def write(path, frames, fps=1):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*'mp4v'), fps, (400, 200))
    for frame in frames: writer.write(frame)
    writer.release(); return path


def test_job_reference_must_match_its_hash(cv_case):
    from aifootball.processor.job import read_job
    from aifootball.analytics.exchange import ExchangeError
    job, _, _, _ = cv_case
    assert read_job(with_reference(job, textured()))
    with pytest.raises(ExchangeError, match='Эталонный кадр'):
        read_job(with_reference(job, textured(), sha='0' * 64))


def test_alignment_is_recorded_and_reported(cv_case, tmp_path):
    from aifootball.processor.cv import run_cv
    from aifootball.processor.job import package_result
    from aifootball.analytics.exchange import validate_result
    job, video, models, ws = cv_case
    root = run_cv(with_reference(job, textured()), video, ws('flat'), models=models)
    alignment = json.loads((root / 'meta.json').read_text())['camera_alignment']
    assert alignment['status'] == 'unverified'          # однотонное видео: сверять не по чему
    result = validate_result(package_result(job, video, root, tmp_path / 'r.zip'))
    assert result.checks['camera_alignment']['status'] == 'unverified'
    assert any('сверить положение камеры' in w for w in result.checks['warnings']) and result.checks['critical_errors'] == []


def test_camera_moved_too_far_stops_before_detection(cv_case, tmp_path):
    from aifootball.processor.cv import run_cv
    job, _, models, ws = cv_case
    reference = textured()
    moved = cv2.warpAffine(reference, np.float32([[1, 0, 70], [0, 1, 0]]), (400, 200), borderMode=cv2.BORDER_REFLECT)
    video = write(tmp_path / 'moved.mp4', [moved] * 30)
    Predictor.calls = 0
    with pytest.raises(ValueError, match='новую версию профиля'):
        run_cv(with_reference(job, reference), video, ws('moved'), models=models)
    assert Predictor.calls == 0
