import json
from uuid import uuid4
from zipfile import ZipFile

import polars as pl
import pytest
import yaml

from aifootball import schemas
from conftest import write_video
from report_fixtures import synthetic_match


def job_package(venue, tmp_path):
    from hashlib import sha256

    camera_id, hall_id = str(uuid4()), str(uuid4())
    context = {
        'match_id': str(uuid4()),
        'hall_id': hall_id,
        'pitch': {'length_m': venue.length_m, 'width_m': venue.width_m},
        'camera': {
            'id': camera_id,
            'version': 1,
            'frame_width': 400,
            'frame_height': 200,
            'homography': venue.H.tolist(),
            'polygon_px': venue.pitch_polygon_px.tolist(),
            'calibration': None,
        },
        'rosters': [],
        'teams': {'home': {'id': str(uuid4()), 'name': 'Хозяева'}, 'away': {'id': str(uuid4()), 'name': 'Гости'}},
        'units': {'distance': 'm', 'speed': 'm/s', 'time': 's', 'heatmap': 's'},
    }
    hashed = sha256(json.dumps(context, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    job = {
        'contract_version': '1',
        'job_id': str(uuid4()),
        'match_id': context['match_id'],
        'context_hash': hashed,
        'context': context,
    }
    path = tmp_path / 'job.zip'
    cfg = yaml.safe_load((venue.root / 'venue.yaml').read_text())
    cfg['venue_id'] = hall_id
    cfg['processing'].update(frame_width=400, frame_height=200, camera_profile_id=camera_id)
    with ZipFile(path, 'w') as archive:
        archive.writestr('job.json', json.dumps(job))
        archive.writestr('venue.yaml', yaml.safe_dump(cfg))
        archive.writestr('homography.json', json.dumps({'H': context['camera']['homography']}))
        archive.writestr('pitch_polygon.json', json.dumps({'points_px': context['camera']['polygon_px']}))
    return path, job


def test_package_has_real_thumbnails_short_tracks_and_absolute_times(venue, tmp_path):
    from aifootball.analytics.exchange import validate_result
    from aifootball.processor.job import package_result

    path, job = job_package(venue, tmp_path)
    video = write_video(tmp_path / 'source.mp4', n_frames=400, fps=2, size=(400, 200))
    state, tracks = synthetic_match(seconds=180)
    # One fragment remains short and all timestamps retain original-video offset.
    state = state.filter((pl.col('track_id') != 1) | (pl.col('ts') < 10)).with_columns(ts=pl.col('ts') + 10)
    tracks = tracks.filter((pl.col('track_id') != 1) | (pl.col('ts') < 10)).with_columns(
        ts=pl.col('ts') + 10, frame_id=pl.col('frame_id') + 20
    )
    work = tmp_path / 'artifacts'
    schemas.write(state, work / 'state.parquet', 'state')
    schemas.write(tracks, work / 'tracks.parquet', 'tracks')
    out = package_result(path, video, work, tmp_path / 'result.zip')
    result = validate_result(out)
    assert result.manifest['job_id'] == job['job_id']
    short = next(t for t in result.tracks['tracks'] if t['track_id'] == 1)
    assert short['intervals'][0][0] == 10
    assert short['has_metrics'] is False
    assert short['thumb'] is not None
    assert result.files[short['thumb']].startswith(b'\xff\xd8')
    assert result.checks['partial']
    assert str(video).encode() not in result.files['manifest.json']
    assert all(not name.endswith('.mp4') for name in result.files)


def test_job_rejects_changed_cv_geometry_and_source_resolution(venue, tmp_path):
    from aifootball.analytics.exchange import ExchangeError
    from aifootball.processor.job import package_result, read_job

    path, job = job_package(venue, tmp_path)
    video = write_video(tmp_path / 'wrong.mp4')
    with pytest.raises(ExchangeError, match='разрешение'):
        package_result(path, video, tmp_path, tmp_path / 'result.zip')
    files = {}
    with ZipFile(path) as source:
        files = {n: source.read(n) for n in source.namelist()}
    files['homography.json'] = json.dumps({'H': [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}).encode()
    with ZipFile(path, 'w') as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    with pytest.raises(ExchangeError, match='геометр'):
        read_job(path)


def rewritten_job(path, out, change):
    """Тот же пакет задания с изменённым контекстом: новое задание со своим отпечатком контекста."""
    from hashlib import sha256

    with ZipFile(path) as source:
        files = {n: source.read(n) for n in source.namelist()}
    job = json.loads(files['job.json'])
    change(job['context'])
    job['job_id'] = str(uuid4())
    job['context_hash'] = sha256(
        json.dumps(job['context'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    ).hexdigest()
    files['job.json'] = json.dumps(job).encode()
    with ZipFile(out, 'w') as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    return out, job


def test_artifacts_of_previous_job_are_repackaged_when_only_the_roster_changed(venue, tmp_path):
    from aifootball.analytics.exchange import ExchangeError, validate_result
    from aifootball.processor.job import process_job, read_job, source_for_job

    old_path, old = job_package(venue, tmp_path)
    player = {'player_id': str(uuid4()), 'side': 'home', 'display_name': 'Игрок', 'shirt_number': '8'}
    new_path, new = rewritten_job(old_path, tmp_path / 'job-roster.zip', lambda c: c['rosters'].append(player))
    teams_path, _ = rewritten_job(
        old_path, tmp_path / 'job-teams.zip', lambda c: c['teams']['home'].update(name='Другие')
    )
    video = write_video(tmp_path / 'clip.mp4', n_frames=140, fps=2, size=(400, 200))
    state, tracks = synthetic_match(seconds=65, sprint=False)
    work = tmp_path / 'artifacts'
    schemas.write(state, work / 'state.parquet', 'state')
    schemas.write(tracks, work / 'tracks.parquet', 'tracks')
    meta = {
        'camera_profile_id': old['context']['camera']['id'],
        'source_sha256': source_for_job(read_job(old_path), video)['sha256'],
        'context_hash': old['context_hash'],
    }
    (work / 'meta.json').write_text(json.dumps(meta))

    with pytest.raises(ExchangeError, match='происхождение'):
        process_job(new_path, video, tmp_path / 'plain.zip', artifacts=work)
    result = validate_result(
        process_job(new_path, video, tmp_path / 'result.zip', artifacts=work, artifacts_job=old_path)
    )
    assert result.manifest['job_id'] == new['job_id']
    # Изменились не только игроки — артефакты прежнего задания к новому не подходят.
    with pytest.raises(ExchangeError, match='не только составом'):
        process_job(teams_path, video, tmp_path / 'teams.zip', artifacts=work, artifacts_job=old_path)
    # Прежнее задание — то, под которым получены артефакты, а не любое с тем же составом.
    with pytest.raises(ExchangeError, match='происхождение'):
        process_job(new_path, video, tmp_path / 'self.zip', artifacts=work, artifacts_job=new_path)


def test_artifacts_job_needs_artifacts():
    from aifootball.analytics.exchange import ExchangeError
    from aifootball.processor.job import process_job

    with pytest.raises(ExchangeError, match='--artifacts-job'):
        process_job('job.zip', 'clip.mp4', 'result.zip', artifacts_job='old.zip')


def test_cli_takes_the_job_artifacts_were_made_for():
    from pathlib import Path

    from aifootball.cli import build_parser

    args = build_parser().parse_args(
        ['process-job', '--job', 'job.zip', '--video', 'a.mp4', '--output', 'r.zip']
        + ['--artifacts', 'work', '--artifacts-job', 'old.zip']
    )
    assert args.artifacts_job == Path('old.zip')


def test_process_job_cli_exists():
    from aifootball.cli import build_parser

    args = build_parser().parse_args(['process-job', '--job', 'job.zip', '--video', 'a.mp4', '--output', 'result.zip'])
    assert args.command == 'process-job'


def test_operator_can_mark_fragment_recording():
    from aifootball.cli import build_parser

    args = build_parser().parse_args(
        ['process-job', '--job', 'job.zip', '--video', 'clip.mp4', '--output', 'result.zip', '--partial-recording']
    )
    assert args.partial_recording is True


@pytest.mark.parametrize('mode', ['unknown_speed', 'missing_team'])
def test_package_preserves_missing_metrics_with_reasons(venue, tmp_path, mode):
    from aifootball.analytics.exchange import validate_result
    from aifootball.processor.job import package_result

    path, job = job_package(venue, tmp_path)
    video = write_video(tmp_path / 'clip.mp4', n_frames=140, fps=2, size=(400, 200))
    state, tracks = synthetic_match(seconds=65, sprint=False)
    if mode == 'unknown_speed':
        state = state.with_columns(speed=pl.lit(venue.max_physical_speed))
    else:
        state = state.filter(pl.col('team') == 'A')
        tracks = tracks.filter(pl.col('team') == 'A')
    work = tmp_path / 'artifacts'
    schemas.write(state, work / 'state.parquet', 'state')
    schemas.write(tracks, work / 'tracks.parquet', 'tracks')
    result = validate_result(package_result(path, video, work, tmp_path / 'result.zip'))
    primary = result.report['periods'][0]
    if mode == 'unknown_speed':
        assert primary['players'][0]['vmax_ms'] is None
        assert primary['players'][0]['metric_notes']['vmax_ms']
    else:
        assert primary['teams']['B']['distance_m'] is None
        assert primary['teams']['B']['metric_notes']['distance_m']
