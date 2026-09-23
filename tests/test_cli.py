import json

import polars as pl

from aifootball import schemas
from aifootball.cli import main


def _runner_detections():
    """Два игрока бегут внутри поля (0..400 x 0..200 px), 3 секунды при 10 fps."""
    rows = []
    for f in range(30):
        for x0, a in ((20, 60.0), (200, 200.0)):
            rows.append({
                "frame_id": f, "ts": f / 10, "cls": "person",
                "x1": x0 + 3.0 * f, "y1": 40.0, "x2": x0 + 3.0 * f + 20, "y2": 90.0, "conf": 0.9,
                "torso_l": 120.0, "torso_a": a, "torso_b": 140.0,
            })
    return pl.DataFrame(rows, schema=schemas.DETECTIONS)


def test_steps_after_detection_produce_all_artifacts(venue, tiny_video, tmp_path):
    match = tmp_path / "match"
    schemas.write(_runner_detections(), match / "detections.parquet", "detections")
    common = ["--venue", str(venue.root), "--match", str(match)]

    for step in ("track", "project", "metrics"):
        assert main([step, *common]) == 0
    check_code = main(["check", *common])
    assert main(["render", *common, "--video", str(tiny_video), "--seconds", "1"]) == 0

    tracks = schemas.read(match / "tracks.parquet", "tracks")
    assert tracks["track_id"].n_unique() == 2
    assert sorted(tracks["team"].unique().to_list()) == ["A", "B"]
    metrics = json.loads((match / "metrics.json").read_text())
    assert metrics["teams"]["A"]["distance_m"] > 0
    checks = json.loads((match / "checks.json").read_text())
    assert checks["passed"] and check_code == 0  # 3 px/кадр = 3 м/с при масштабе 10 px/м
    assert (match / "debug.mp4").exists()
