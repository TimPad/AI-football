import json

import polars as pl
import pytest

from aifootball import schemas


def _state_row(**overrides):
    row = {
        "frame_id": 3, "ts": 0.3, "track_id": 7, "role": "player", "team": "A",
        "x_m": 1.5, "y_m": 2.5, "vx": 0.1, "vy": 0.2, "speed": 0.22, "interpolated": False,
    }
    row.update(overrides)
    return row


def test_roundtrip_keeps_values_and_types(tmp_path):
    df = pl.DataFrame([_state_row(), _state_row(frame_id=4, team=None)])
    path = tmp_path / "state.parquet"

    schemas.write(df, path, "state")
    back = schemas.read(path, "state")

    assert back.schema == pl.Schema(schemas.STATE)
    assert back["team"].to_list() == ["A", None]
    assert back["frame_id"].to_list() == [3, 4]


def test_read_rejects_other_kind(tmp_path):
    path = tmp_path / "state.parquet"
    schemas.write(pl.DataFrame([_state_row()]), path, "state")

    with pytest.raises(schemas.SchemaError, match="ожидалась схема tracks:1"):
        schemas.read(path, "tracks")


def test_read_rejects_foreign_parquet(tmp_path):
    path = tmp_path / "foreign.parquet"
    pl.DataFrame([_state_row()]).write_parquet(path)

    with pytest.raises(schemas.SchemaError, match="нет метки"):
        schemas.read(path, "state")


def test_write_rejects_missing_columns(tmp_path):
    df = pl.DataFrame([_state_row()]).drop("speed")

    with pytest.raises(schemas.SchemaError, match="speed"):
        schemas.write(df, tmp_path / "state.parquet", "state")


def test_write_leaves_no_temp_file(tmp_path):
    schemas.write(pl.DataFrame([_state_row()]), tmp_path / "state.parquet", "state")
    schemas.write_json({"a": 1}, tmp_path / "metrics.json")

    assert sorted(p.name for p in tmp_path.iterdir()) == ["metrics.json", "state.parquet"]
    assert json.loads((tmp_path / "metrics.json").read_text()) == {"a": 1}


def test_empty_frame_has_schema():
    assert schemas.empty("detections").schema == pl.Schema(schemas.DETECTIONS)
