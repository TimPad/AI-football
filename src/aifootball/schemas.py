"""Схемы артефактов матча и их чтение/запись.

Слои пайплайна общаются только через эти файлы. Версия схемы лежит в метаданных
parquet: шаг, получивший файл другой версии или другого вида, падает сразу,
а не считает мусор.
"""

import json
import os
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

SCHEMA_VERSION = "1"
_META_KEY = b"aifootball"

DETECTIONS = {
    "frame_id": pl.Int32,
    "ts": pl.Float64,
    "cls": pl.Utf8,  # person | ball
    "x1": pl.Float32,
    "y1": pl.Float32,
    "x2": pl.Float32,
    "y2": pl.Float32,
    "conf": pl.Float32,
    # Медианный цвет торса в Lab (шкала OpenCV, 0..255). У мяча — NaN.
    "torso_l": pl.Float32,
    "torso_a": pl.Float32,
    "torso_b": pl.Float32,
}

TRACKS = {
    **DETECTIONS,
    "track_id": pl.Int32,
    # Точка касания пола: центр нижней грани бокса, в пикселях исходного кадра.
    "foot_x": pl.Float32,
    "foot_y": pl.Float32,
    "in_pitch": pl.Boolean,
    "role": pl.Utf8,  # player | goalkeeper | referee | unknown
    "team": pl.Utf8,  # A | B | null
}

STATE = {
    "frame_id": pl.Int32,
    "ts": pl.Float64,
    "track_id": pl.Int32,
    "role": pl.Utf8,
    "team": pl.Utf8,
    "x_m": pl.Float32,
    "y_m": pl.Float32,
    "vx": pl.Float32,
    "vy": pl.Float32,
    "speed": pl.Float32,
    "interpolated": pl.Boolean,
}

SCHEMAS = {"detections": DETECTIONS, "tracks": TRACKS, "state": STATE}


class SchemaError(Exception):
    pass


def empty(kind: str) -> pl.DataFrame:
    return pl.DataFrame(schema=SCHEMAS[kind])


def write(df: pl.DataFrame, path: Path, kind: str) -> None:
    schema = SCHEMAS[kind]
    _check_columns(df, schema, kind)
    table = df.select([pl.col(name).cast(dtype) for name, dtype in schema.items()]).to_arrow()
    metadata = dict(table.schema.metadata or {})
    metadata[_META_KEY] = _tag(kind)
    table = table.replace_schema_metadata(metadata)
    _atomic(path, lambda tmp: pq.write_table(table, tmp))


def read(path: Path, kind: str) -> pl.DataFrame:
    table = pq.read_table(path)
    found = (table.schema.metadata or {}).get(_META_KEY)
    if found != _tag(kind):
        got = found.decode() if found else "нет метки"
        raise SchemaError(f"{path}: ожидалась схема {_tag(kind).decode()}, в файле {got}")
    df = pl.from_arrow(table)
    _check_columns(df, SCHEMAS[kind], kind)
    return df


def write_json(data: dict, path: Path) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    _atomic(path, lambda tmp: tmp.write_text(text, encoding="utf-8"))


def _tag(kind: str) -> bytes:
    return f"{kind}:{SCHEMA_VERSION}".encode()


def _check_columns(df: pl.DataFrame, schema: dict, kind: str) -> None:
    missing = set(schema) - set(df.columns)
    if missing:
        raise SchemaError(f"{kind}: не хватает колонок {sorted(missing)}")


def _atomic(path: Path, write_to) -> None:
    """Пишем во временный файл и переименовываем: прерванный прогон не оставит полуфайл."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    write_to(tmp)
    os.replace(tmp, path)
