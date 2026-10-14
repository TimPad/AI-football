import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from report_fixtures import synthetic_match  # noqa: E402

from aifootball import schemas  # noqa: E402
from aifootball.cli import main  # noqa: E402


def test_report_command_writes_html_and_json(venue, tmp_path):
    match = tmp_path / "match"
    state, tracks = synthetic_match()
    schemas.write(state, match / "state.parquet", "state")
    schemas.write(tracks, match / "tracks.parquet", "tracks")

    code = main(["report", "--venue", str(venue.root), "--match", str(match),
                 "--halves", "0:00-1:40,1:40-3:19", "--team-a", "Зелёные", "--team-b", "Оранжевые"])

    assert code == 0
    data = json.loads((match / "report.json").read_text(encoding="utf-8"))
    assert [p["key"] for p in data["periods"]] == ["all", "h1", "h2"]
    html = (match / "report.html").read_text(encoding="utf-8")
    assert "Зелёные — Оранжевые" in html and "<img" not in html



import pytest
from conftest import write_video


def _match(tmp_path, seconds=2):
    match = tmp_path / 'match'
    state, tracks = synthetic_match(seconds=seconds, sprint=False)
    schemas.write(state, match / 'state.parquet', 'state')
    schemas.write(tracks, match / 'tracks.parquet', 'tracks')
    return match


def test_report_uses_source_duration_without_images(venue, tmp_path):
    match = _match(tmp_path)
    video = write_video(tmp_path / 'source.mp4', n_frames=250)
    (match / 'meta.json').write_text(json.dumps({'video': str(video)}))
    assert main(['report', '--venue', str(venue.root), '--match', str(match)]) == 0
    data = json.loads((match / 'report.json').read_text())
    assert data['match']['video_s'] == 10.
    assert data['match']['processed_s'] == 2.
    assert not data['match']['video_duration_estimated']
    assert '<img' not in (match / 'report.html').read_text()


def test_report_marks_estimated_source_duration(venue, tmp_path):
    match = _match(tmp_path)
    main(['report', '--venue', str(venue.root), '--match', str(match)])
    data = json.loads((match / 'report.json').read_text())
    assert data['match']['video_s'] == 2.
    assert data['match']['video_duration_estimated']


def test_report_rejects_empty_artifacts(venue, tmp_path):
    match = tmp_path / 'empty'
    schemas.write(schemas.empty('state'), match / 'state.parquet', 'state')
    schemas.write(schemas.empty('tracks'), match / 'tracks.parquet', 'tracks')
    with pytest.raises(ValueError, match='нет'):
        main(['report', '--venue', str(venue.root), '--match', str(match)])
    assert not (match / 'report.html').exists()


def test_report_rejects_halves_beyond_processed_data(venue, tmp_path):
    match = _match(tmp_path)
    (match / 'meta.json').write_text(json.dumps({'video_s': 600.}))
    with pytest.raises(ValueError, match='обработан'):
        main(['report', '--venue', str(venue.root), '--match', str(match), '--halves', '0:00-5:00'])


def test_automatic_period_tolerates_float_roundoff_at_start(venue, tmp_path):
    import polars as pl
    match = _match(tmp_path)
    for kind in ('tracks', 'state'):
        path = match / f'{kind}.parquet'
        data = schemas.read(path, kind).with_columns(ts=pl.col('ts') + .5 + 1e-12)
        schemas.write(data, path, kind)
    assert main(['report', '--venue', str(venue.root), '--match', str(match)]) == 0


def test_report_accepts_late_first_detections(venue, tmp_path):
    import polars as pl
    match = _match(tmp_path)
    for kind in ('tracks', 'state'):
        path = match / f'{kind}.parquet'
        data = schemas.read(path, kind).with_columns(ts=pl.col('ts') + 3.)
        schemas.write(data, path, kind)
    assert main(['report', '--venue', str(venue.root), '--match', str(match)]) == 0
    data = json.loads((match / 'report.json').read_text())
    assert data['match']['processed_s'] == 2.


def test_report_fallback_limits_period_to_available_data(venue, tmp_path):
    import polars as pl
    match = _match(tmp_path)
    for kind in ('tracks', 'state'):
        path = match / f'{kind}.parquet'
        data = schemas.read(path, kind).filter(pl.col('track_id') == 11)
        schemas.write(data, path, kind)
    (match / 'meta.json').write_text(json.dumps({'video_s': 600.}))
    assert main(['report', '--venue', str(venue.root), '--match', str(match)]) == 0
    data = json.loads((match / 'report.json').read_text())
    assert data['periods'][0]['duration_s'] == 2.
    assert data['match']['video_s'] == 600.


def test_report_with_ball_renders_caveat_and_accuracy(venue, tmp_path):
    match = _match(tmp_path)
    schemas.write(schemas.empty('detections'), match / 'detections.parquet', 'detections')
    assert main(['report', '--venue', str(venue.root), '--match', str(match), '--with-ball']) == 0
    data = json.loads((match / 'report.json').read_text())
    assert 'ball' in data['periods'][0]
    html = (match / 'report.html').read_text()
    assert 'приблизительно' in html and 'Точность передач' in html
