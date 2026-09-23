# Фаза 1 — вертикальный срез: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Цель:** одна команда прогоняет 5-минутный фрагмент матча из Костромы через все слои — детекция, трекинг, команды, проекция в метры, метрики — и собирает отладочное видео «кадр + вид сверху».

**Архитектура:** пакет `aifootball` из четырёх слоёв, которые общаются только через файлы с версионированной схемой: `detections.parquet` → `tracks.parquet` → `state.parquet` → `metrics.json`. Всё, что зависит от камеры, лежит в `configs/venues/<id>/`. Каждый шаг — отдельная подкоманда CLI.

**Стек:** Python 3.12, uv, ultralytics (YOLO11m на MPS), trackers (ByteTrack), supervision (контейнер детекций), OpenCV 5, polars + pyarrow, pytest.

**Спека:** [docs/specs/2026-09-23-futsal-analytics-design.md](../specs/2026-09-23-futsal-analytics-design.md), разделы 4 и 5 (Ф1).

---

## Как пользоваться планом

- Весь код ниже **уже прогнан**: собран в песочнице и проверен на установленных версиях библиотек. Результат — 60 быстрых тестов и медленный тест на настоящем видео, все зелёные. Пройден и сквозной прогон на минуте настоящего матча: детекция идёт ~11.5 кадр/с, минута видео обрабатывается за 52 с. Если тест падает, ищите опечатку при переносе, а не ошибку в плане.
- Команды запускаются из корня репозитория `/Users/timofeynikulin/AI-football`.
- Задача 21 — **ручная**: инструменту разметки нужны клики мышью. Её делает человек, не агент.
- Фаза 2 (валидационный набор) — отдельный план. Он пишется после этой фазы: предразметка для CVAT строится из её артефактов.

## Карта файлов

| Файл | Ответственность |
|---|---|
| `pyproject.toml` | зависимости, пакет, настройки pytest |
| `src/aifootball/schemas.py` | схемы артефактов, атомарная запись, проверка версии |
| `src/aifootball/venue.py` | загрузка конфига установки камеры |
| `src/aifootball/geometry/polygons.py` | точка внутри контура поля |
| `src/aifootball/geometry/undistort.py` | снятие дисторсии с точек |
| `src/aifootball/geometry/homography.py` | пиксели пола → метры, честная ошибка leave-one-out |
| `src/aifootball/perception/frames.py` | чтение видео с прореживанием по времени |
| `src/aifootball/perception/color.py` | цвет формы (торс) в Lab |
| `src/aifootball/perception/detect.py` | L1: YOLO → `detections.parquet` |
| `src/aifootball/perception/track.py` | L1: ByteTrack, точка касания пола, флаг «на поле» |
| `src/aifootball/perception/teams.py` | две команды по цвету формы (базово) |
| `src/aifootball/state/smooth.py` | сглаживание, короткие пропуски, скорости |
| `src/aifootball/state/project.py` | L2: `tracks` → `state` в метрах |
| `src/aifootball/analytics/metrics.py` | L3: дистанции, покрытие, тепловые карты |
| `src/aifootball/analytics/checks.py` | критерии готовности фазы 1 |
| `src/aifootball/viz/topdown.py` | схема поля сверху |
| `src/aifootball/viz/overlay.py` | боксы треков на кадре |
| `src/aifootball/viz/debug_video.py` | отладочное видео «кадр + вид сверху» |
| `src/aifootball/tools/marking.py` | сохранение разметки, предпросмотр гомографии |
| `src/aifootball/tools/mark_points.py` | окно для разметки мышью |
| `src/aifootball/cli.py` | подкоманды пайплайна |
| `configs/venues/kostroma/` | конфиг установки Костромы |

---

### Задача 1. Каркас проекта

Пакет, зависимости, pytest. Веса YOLO переезжают из корня в `models/`.

**Файлы:**
- Создать: `pyproject.toml`, `src/aifootball/__init__.py` и `__init__.py` в подпакетах `geometry`, `perception`, `state`, `analytics`, `viz`, `tools`
- Изменить: `scripts/bench_detect.py`, `scripts/debug_overlay.py` — пути к весам

- [ ] **Шаг 1. `pyproject.toml`**

```toml
[project]
name = "aifootball"
version = "0.1.0"
description = "Аналитика футзальных матчей по видео со статичной камеры"
requires-python = ">=3.12"
dependencies = [
    "ultralytics>=8.4",
    "trackers>=2.6",
    "supervision>=0.30",
    "polars>=1.40",
    "pyarrow>=20",
    "pyyaml>=6",
    "numpy>=2.0",
    "opencv-python>=4.10",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/aifootball"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["slow: прогон на настоящем видео с YOLO, минуты"]
addopts = "-m 'not slow'"
```

`addopts = "-m 'not slow'"`: медленный тест на настоящем видео по умолчанию не запускается, только явно через `-m slow`.

- [ ] **Шаг 2. Пустые пакеты и каталоги**

```bash
mkdir -p src/aifootball/{geometry,perception,state,analytics,viz,tools} tests models
for d in "" geometry perception state analytics viz tools; do touch src/aifootball/$d/__init__.py; done
```

- [ ] **Шаг 3. Веса моделей — в `models/`**

```bash
mv yolo11n.pt yolo11s.pt yolo11m.pt models/
sed -i '' 's|MODELS = \["yolo11n.pt", "yolo11s.pt", "yolo11m.pt"\]|MODELS = ["models/yolo11n.pt", "models/yolo11s.pt", "models/yolo11m.pt"]|' scripts/bench_detect.py
sed -i '' 's|^MODEL = "yolo11m.pt"|MODEL = "models/yolo11m.pt"|' scripts/debug_overlay.py
grep -n "models/" scripts/*.py
```

Ожидается: по одной найденной строке в каждом скрипте. `models/` уже в `.gitignore`.

- [ ] **Шаг 4. Установка пакета в режиме разработки**

```bash
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest -q
```

Ожидается: установлен `aifootball==0.1.0`; pytest пишет `no tests ran` — тестов пока нет, это нормально.

- [ ] **Шаг 5. Коммит**

```bash
git add pyproject.toml src/aifootball scripts/bench_detect.py scripts/debug_overlay.py
git commit -m "Каркас пакета aifootball" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 2. Схемы артефактов

Контракт между слоями. Версия схемы пишется в метаданные parquet, и файл чужой версии или вида при чтении отвергается сразу. Запись атомарная: сначала во временный файл, потом переименование.

**Файлы:**
- Создать: `src/aifootball/schemas.py`
- Тест: `tests/test_schemas.py`

- [ ] **Шаг 1. Тест `tests/test_schemas.py`**

```python
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
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_schemas.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.schemas'`

- [ ] **Шаг 3. Реализация `src/aifootball/schemas.py`**

```python
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
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_schemas.py -v`

Ожидается: `6 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/schemas.py tests/test_schemas.py
git commit -m "Схемы артефактов с версией и атомарной записью" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 3. Конфиг установки камеры и общие фикстуры тестов

`Venue` — всё, что зависит от зала и точки съёмки. Контур поля и гомография необязательны при загрузке: детекцию можно запускать до разметки. Шаги, которым они нужны, вызывают `require_polygon()` / `require_homography()` и падают с подсказкой, какую команду запустить.

`tests/conftest.py` задаёт тестовую установку с масштабом «10 px = 1 м» и синтетическое видео — на них опираются тесты следующих задач.

**Файлы:**
- Создать: `src/aifootball/venue.py`
- Тест: `tests/conftest.py`, `tests/test_venue.py`

- [ ] **Шаг 1. Общие фикстуры `tests/conftest.py`**

```python
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

from aifootball.venue import load_venue

VENUE_YAML = {
    "venue_id": "test",
    "pitch": {"length_m": 40.0, "width_m": 20.0},
    "processing": {
        "target_fps": 10,
        "model": "yolo11m.pt",
        "imgsz": 1280,
        "conf_person": 0.25,
        "conf_ball": 0.10,
    },
}

# Масштаб «10 пикселей = 1 метр»: удобно считать ожидаемые значения в тестах.
SCALE_H = [[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, 0.0, 1.0]]


def make_venue_dir(root: Path, polygon=None, H=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "venue.yaml").write_text(yaml.safe_dump(VENUE_YAML), encoding="utf-8")
    if polygon is not None:
        (root / "pitch_polygon.json").write_text(json.dumps({"points_px": polygon}))
    if H is not None:
        (root / "homography.json").write_text(json.dumps({"H": H, "points": []}))
    return root


def write_video(path: Path, n_frames: int = 50, fps: float = 25.0, size=(320, 240)) -> Path:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"mp4v"), fps, size)
    for i in range(n_frames):
        writer.write(np.full((size[1], size[0], 3), (i * 5) % 256, dtype=np.uint8))
    writer.release()
    return path


@pytest.fixture
def venue(tmp_path):
    """Установка с полем 0..400 x 0..200 px и масштабом 10 px = 1 м."""
    polygon = [[0, 0], [400, 0], [400, 200], [0, 200]]
    return load_venue(make_venue_dir(tmp_path / "venue", polygon=polygon, H=SCALE_H))


@pytest.fixture
def tiny_video(tmp_path):
    return write_video(tmp_path / "tiny.mp4")
```

- [ ] **Шаг 2. Тест `tests/test_venue.py`**

```python
import numpy as np
import pytest

from aifootball.venue import load_venue
from conftest import SCALE_H, make_venue_dir


def test_loads_yaml_and_optional_files(tmp_path):
    root = make_venue_dir(tmp_path / "v", polygon=[[0, 0], [10, 0], [10, 10]], H=SCALE_H)

    venue = load_venue(root)

    assert venue.venue_id == "test"
    assert (venue.length_m, venue.width_m) == (40.0, 20.0)
    assert venue.target_fps == 10.0
    assert venue.pitch_polygon_px.shape == (3, 2)
    np.testing.assert_allclose(venue.H, SCALE_H)
    assert venue.calib is None


def test_missing_markup_is_none_until_required(tmp_path):
    venue = load_venue(make_venue_dir(tmp_path / "v"))

    assert venue.pitch_polygon_px is None and venue.H is None
    with pytest.raises(FileNotFoundError, match="mark_points polygon"):
        venue.require_polygon()
    with pytest.raises(FileNotFoundError, match="mark_points homography"):
        venue.require_homography()
```

- [ ] **Шаг 3. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_venue.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.venue'` (падает уже импорт в `conftest.py`).

- [ ] **Шаг 4. Реализация `src/aifootball/venue.py`**

```python
"""Конфиг установки камеры: всё, что зависит от конкретного зала и точки съёмки.

Каталог установки `configs/venues/<venue_id>/`:
  venue.yaml          — размеры поля и параметры обработки (пишется руками)
  pitch_polygon.json  — контур поля на кадре (размечается инструментом mark_points)
  homography.json     — пиксели -> метры (размечается инструментом mark_points)
  calib.json          — дисторсия объектива (необязательно)
"""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml


@dataclass(frozen=True)
class Calibration:
    K: np.ndarray  # матрица камеры 3x3
    dist: np.ndarray  # коэффициенты дисторсии OpenCV


@dataclass(frozen=True)
class Venue:
    root: Path
    venue_id: str
    length_m: float
    width_m: float
    target_fps: float
    model: str
    imgsz: int
    conf_person: float
    conf_ball: float
    pitch_polygon_px: np.ndarray | None
    H: np.ndarray | None
    calib: Calibration | None

    def require_polygon(self) -> np.ndarray:
        if self.pitch_polygon_px is None:
            raise FileNotFoundError(
                f"{self.root / 'pitch_polygon.json'}: контур поля не размечен. "
                f"Запустите: python -m aifootball.tools.mark_points polygon ..."
            )
        return self.pitch_polygon_px

    def require_homography(self) -> np.ndarray:
        if self.H is None:
            raise FileNotFoundError(
                f"{self.root / 'homography.json'}: гомография не размечена. "
                f"Запустите: python -m aifootball.tools.mark_points homography ..."
            )
        return self.H


def load_venue(root: Path) -> Venue:
    cfg = yaml.safe_load((root / "venue.yaml").read_text(encoding="utf-8"))
    pitch = cfg["pitch"]
    proc = cfg["processing"]
    return Venue(
        root=root,
        venue_id=cfg["venue_id"],
        length_m=float(pitch["length_m"]),
        width_m=float(pitch["width_m"]),
        target_fps=float(proc["target_fps"]),
        model=proc["model"],
        imgsz=int(proc["imgsz"]),
        conf_person=float(proc["conf_person"]),
        conf_ball=float(proc["conf_ball"]),
        pitch_polygon_px=_load_polygon(root / "pitch_polygon.json"),
        H=_load_homography(root / "homography.json"),
        calib=_load_calibration(root / "calib.json"),
    )


def _load_polygon(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    points = json.loads(path.read_text(encoding="utf-8"))["points_px"]
    return np.asarray(points, dtype=np.float32)


def _load_homography(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    return np.asarray(json.loads(path.read_text(encoding="utf-8"))["H"], dtype=np.float64)


def _load_calibration(path: Path) -> Calibration | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Calibration(
        K=np.asarray(data["K"], dtype=np.float64),
        dist=np.asarray(data["dist"], dtype=np.float64),
    )
```

- [ ] **Шаг 5. Тест зелёный**

Запуск: `.venv/bin/python -m pytest -q`

Ожидается: `8 passed` — 2 новых плюс 6 из задачи 2.

- [ ] **Шаг 6. Коммит**

```bash
git add src/aifootball/venue.py tests/conftest.py tests/test_venue.py
git commit -m "Конфиг установки камеры" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 4. Точка внутри контура поля

Фильтр детекций по зоне поля. По замерам он убирает две трети детекций — зрителей на балконе.

**Файлы:**
- Создать: `src/aifootball/geometry/polygons.py`
- Тест: `tests/test_polygons.py`

- [ ] **Шаг 1. Тест `tests/test_polygons.py`**

```python
import numpy as np

from aifootball.geometry.polygons import points_in_polygon

SQUARE = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float32)


def test_inside_outside_and_boundary():
    points = np.array([[5, 5], [15, 5], [10, 5], [-1, -1]], dtype=np.float32)

    assert points_in_polygon(points, SQUARE).tolist() == [True, False, True, False]


def test_empty_input():
    assert points_in_polygon(np.zeros((0, 2)), SQUARE).shape == (0,)
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_polygons.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.geometry.polygons'`

- [ ] **Шаг 3. Реализация `src/aifootball/geometry/polygons.py`**

```python
"""Проверка «точка внутри контура» — фильтр детекций по зоне поля."""

import cv2
import numpy as np


def points_in_polygon(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    """True для точек внутри многоугольника или на его границе.

    points: (N, 2), polygon: (M, 2) — в одной системе координат.
    """
    if len(points) == 0:
        return np.zeros(0, dtype=bool)
    contour = np.asarray(polygon, dtype=np.float32).reshape(-1, 1, 2)
    return np.array(
        [cv2.pointPolygonTest(contour, (float(x), float(y)), False) >= 0 for x, y in points],
        dtype=bool,
    )
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_polygons.py -v`

Ожидается: `2 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/geometry/polygons.py tests/test_polygons.py
git commit -m "Проверка точки внутри контура поля" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 5. Снятие дисторсии с точек

Снимаем дисторсию только с точек касания пола, а не с кадров целиком — так в сотни раз дешевле. Без калибровки (Кострома) точки проходят как есть.

**Файлы:**
- Создать: `src/aifootball/geometry/undistort.py`
- Тест: `tests/test_undistort.py`

- [ ] **Шаг 1. Тест `tests/test_undistort.py`**

```python
import cv2
import numpy as np

from aifootball.geometry.undistort import undistort_points
from aifootball.venue import Calibration

K = np.array([[800.0, 0, 640], [0, 800.0, 360], [0, 0, 1]])


def _project(points_3d, dist):
    pixels, _ = cv2.projectPoints(points_3d, np.zeros(3), np.zeros(3), K, dist)
    return pixels.reshape(-1, 2)


def test_without_calibration_points_pass_through():
    points = np.array([[10.0, 20.0], [30.0, 40.0]])

    np.testing.assert_allclose(undistort_points(points, None), points)


def test_removes_barrel_distortion():
    dist = np.array([-0.3, 0.1, 0.0, 0.0, 0.0])
    points_3d = np.array([[0.5, 0.3, 1.0], [-0.6, -0.4, 1.0], [0.1, -0.2, 1.0]])
    distorted = _project(points_3d, dist)
    ideal = _project(points_3d, np.zeros(5))

    restored = undistort_points(distorted, Calibration(K=K, dist=dist))

    np.testing.assert_allclose(restored, ideal, atol=0.5)
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_undistort.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.geometry.undistort'`

- [ ] **Шаг 3. Реализация `src/aifootball/geometry/undistort.py`**

```python
"""Снятие дисторсии объектива с точек (не с кадров целиком — так дешевле)."""

import cv2
import numpy as np

from aifootball.venue import Calibration


def undistort_points(points: np.ndarray, calib: Calibration | None) -> np.ndarray:
    """Пиксели исходного кадра -> пиксели идеальной камеры без дисторсии.

    Без калибровки точки возвращаются как есть: для установок со слабой
    дисторсией (Кострома) калибровка не нужна.
    """
    points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if calib is None or len(points) == 0:
        return points
    undistorted = cv2.undistortPoints(points.reshape(-1, 1, 2), calib.K, calib.dist, P=calib.K)
    return undistorted.reshape(-1, 2)
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_undistort.py -v`

Ожидается: `2 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/geometry/undistort.py tests/test_undistort.py
git commit -m "Снятие дисторсии объектива с точек" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 6. Гомография

Пиксели пола → метры. Кроме ошибки на своих точках (при 4 точках она всегда ноль) считается честная ошибка leave-one-out: каждая точка проверяется гомографией, посчитанной без неё.

**Файлы:**
- Создать: `src/aifootball/geometry/homography.py`
- Тест: `tests/test_homography.py`

- [ ] **Шаг 1. Тест `tests/test_homography.py`**

```python
import numpy as np
import pytest

from aifootball.geometry.homography import apply_homography, fit_homography, leave_one_out_error

# Настоящая перспектива: не просто масштаб, а наклон плоскости.
TRUE_H = np.array([[0.05, 0.01, -3.0], [0.002, 0.08, -10.0], [0.0001, 0.0009, 1.0]])
PIXELS = np.array([[100, 400], [1100, 420], [900, 250], [300, 240], [640, 330], [200, 320]], float)


def test_recovers_known_homography():
    meters = apply_homography(TRUE_H, PIXELS)

    H, error = fit_homography(PIXELS, meters)

    assert error < 1e-6
    np.testing.assert_allclose(apply_homography(H, PIXELS), meters, atol=1e-6)


def test_needs_four_points():
    with pytest.raises(ValueError, match="минимум 4"):
        fit_homography(PIXELS[:3], PIXELS[:3])


def test_leave_one_out_catches_bad_point():
    meters = apply_homography(TRUE_H, PIXELS)
    assert leave_one_out_error(PIXELS, meters) < 1e-6

    meters[4] += [2.0, 0.0]  # одна точка размечена с ошибкой в 2 м

    assert leave_one_out_error(PIXELS, meters) > 0.3


def test_empty_points():
    assert apply_homography(TRUE_H, np.zeros((0, 2))).shape == (0, 2)
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_homography.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.geometry.homography'`

- [ ] **Шаг 3. Реализация `src/aifootball/geometry/homography.py`**

```python
"""Гомография «пиксели пола -> метры на поле»."""

import cv2
import numpy as np

MIN_POINTS = 4


def fit_homography(px: np.ndarray, m: np.ndarray) -> tuple[np.ndarray, float]:
    """Считает H по парам точек. Возвращает H и среднюю ошибку на этих же точках, м."""
    px = np.asarray(px, dtype=np.float64).reshape(-1, 2)
    m = np.asarray(m, dtype=np.float64).reshape(-1, 2)
    if len(px) != len(m):
        raise ValueError(f"разное число точек: {len(px)} пикселей и {len(m)} метров")
    if len(px) < MIN_POINTS:
        raise ValueError(f"нужно минимум {MIN_POINTS} точки, дано {len(px)}")
    H, _ = cv2.findHomography(px, m, 0)
    if H is None:
        raise ValueError("точки вырождены (например, три на одной прямой): гомография не считается")
    return H, _mean_error(H, px, m)


def apply_homography(H: np.ndarray, points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(points) == 0:
        return points
    return cv2.perspectiveTransform(points.reshape(-1, 1, 2), H).reshape(-1, 2)


def leave_one_out_error(px: np.ndarray, m: np.ndarray) -> float:
    """Честная ошибка: каждая точка проверяется гомографией, посчитанной без неё.

    Ошибка на тех же точках, по которым считали H, всегда занижена — при четырёх
    точках она просто ноль. Нужно минимум 5 точек.
    """
    px = np.asarray(px, dtype=np.float64).reshape(-1, 2)
    m = np.asarray(m, dtype=np.float64).reshape(-1, 2)
    if len(px) <= MIN_POINTS:
        raise ValueError(f"для проверки нужно больше {MIN_POINTS} точек, дано {len(px)}")
    errors = []
    for i in range(len(px)):
        rest = np.arange(len(px)) != i
        H, _ = fit_homography(px[rest], m[rest])
        errors.append(np.linalg.norm(apply_homography(H, px[i : i + 1])[0] - m[i]))
    return float(np.mean(errors))


def _mean_error(H: np.ndarray, px: np.ndarray, m: np.ndarray) -> float:
    return float(np.mean(np.linalg.norm(apply_homography(H, px) - m, axis=1)))
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_homography.py -v`

Ожидается: `4 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/geometry/homography.py tests/test_homography.py
git commit -m "Гомография с честной оценкой ошибки" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 7. Чтение кадров с прореживанием

Кадры отбираются по времени, а не шагом «каждый N-й»: из 25 fps получается ровно 10, а не 12.5.

**Файлы:**
- Создать: `src/aifootball/perception/frames.py`
- Тест: `tests/test_frames.py`

- [ ] **Шаг 1. Тест `tests/test_frames.py`**

```python
import pytest

from aifootball.perception.frames import iter_frames, video_fps


def test_samples_25fps_down_to_10(tiny_video):
    frames = list(iter_frames(tiny_video, target_fps=10))

    # 50 кадров при 25 fps = 2 секунды -> 20 кадров при 10 fps
    assert len(frames) == 20
    assert [f[0] for f in frames[:5]] == [0, 3, 5, 8, 10]
    assert frames[1][1] == pytest.approx(0.12)
    assert frames[0][2].shape == (240, 320, 3)


def test_target_above_source_keeps_every_frame(tiny_video):
    assert len(list(iter_frames(tiny_video, target_fps=100))) == 50


def test_reports_fps(tiny_video):
    assert video_fps(tiny_video) == pytest.approx(25.0)


def test_missing_file_fails_clearly(tmp_path):
    with pytest.raises(FileNotFoundError, match="не открывается"):
        list(iter_frames(tmp_path / "nope.mp4", target_fps=10))
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_frames.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.perception.frames'`

- [ ] **Шаг 3. Реализация `src/aifootball/perception/frames.py`**

```python
"""Чтение кадров видео с прореживанием до целевого fps."""

from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np


def video_fps(video: Path) -> float:
    cap = _open(video)
    try:
        return cap.get(cv2.CAP_PROP_FPS)
    finally:
        cap.release()


def iter_frames(video: Path, target_fps: float) -> Iterator[tuple[int, float, np.ndarray]]:
    """Отдаёт (номер кадра, время в секундах, кадр BGR) примерно с частотой target_fps.

    Отбор по времени, а не «каждый N-й кадр»: из 25 fps так получается ровно 10,
    а не 12.5, как дал бы шаг 2.
    """
    cap = _open(video)
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if src_fps <= 0:
        cap.release()
        raise ValueError(f"{video}: видео не сообщает fps")
    taken = 0
    frame_id = 0
    try:
        while cap.grab():
            ts = frame_id / src_fps
            if ts + 1e-6 >= taken / target_fps:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                yield frame_id, ts, frame
                taken += 1
            frame_id += 1
    finally:
        cap.release()


def _open(video: Path) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FileNotFoundError(f"не открывается видео: {video}")
    return cap
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_frames.py -v`

Ожидается: `4 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/perception/frames.py tests/test_frames.py
git commit -m "Чтение видео с прореживанием по времени" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 8. Цвет формы

Медианный цвет центральной части торса в Lab — признак для деления на команды. Считается при детекции, пока кадр в памяти.

**Файлы:**
- Создать: `src/aifootball/perception/color.py`
- Тест: `tests/test_color.py`

- [ ] **Шаг 1. Тест `tests/test_color.py`**

```python
import math

import numpy as np

from aifootball.perception.color import torso_lab


def _frame_with_shirt(bgr):
    frame = np.full((200, 200, 3), 120, dtype=np.uint8)  # серый «пол»
    frame[40:100, 60:140] = bgr  # футболка
    return frame


def test_red_shirt_has_high_a():
    _, a, _ = torso_lab(_frame_with_shirt((0, 0, 255)), (50, 20, 150, 200))
    assert a > 170


def test_green_shirt_has_low_a():
    _, a, _ = torso_lab(_frame_with_shirt((0, 200, 0)), (50, 20, 150, 200))
    assert a < 90


def test_box_outside_frame_gives_nan():
    lab = torso_lab(np.zeros((100, 100, 3), np.uint8), (300, 300, 350, 400))
    assert all(math.isnan(v) for v in lab)
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_color.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.perception.color'`

- [ ] **Шаг 3. Реализация `src/aifootball/perception/color.py`**

```python
"""Цвет формы игрока — признак для разделения на команды."""

import math

import cv2
import numpy as np

NAN3 = (math.nan, math.nan, math.nan)


def torso_lab(frame: np.ndarray, box) -> tuple[float, float, float]:
    """Медианный цвет торса в Lab (шкала OpenCV 0..255).

    Берём центральную часть верхней половины бокса: там футболка, а по краям
    бокса — пол и соседние игроки. Медиана устойчива к номеру и полосам на форме.
    """
    x1, y1, x2, y2 = (float(v) for v in box)
    w, h = x2 - x1, y2 - y1
    top, bottom = int(y1 + 0.2 * h), int(y1 + 0.5 * h)
    left, right = int(x1 + 0.3 * w), int(x1 + 0.7 * w)

    frame_h, frame_w = frame.shape[:2]
    top, bottom = max(top, 0), min(bottom, frame_h)
    left, right = max(left, 0), min(right, frame_w)
    if bottom <= top or right <= left:
        return NAN3

    crop = frame[top:bottom, left:right]
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3)
    median = np.median(lab, axis=0)
    return float(median[0]), float(median[1]), float(median[2])
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_color.py -v`

Ожидается: `3 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/perception/color.py tests/test_color.py
git commit -m "Цвет формы игрока в Lab" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 9. Детекция

L1: YOLO по кадрам → `detections.parquet`. Логика отбора (`boxes_to_rows`) вынесена в чистую функцию и тестируется без модели. У каждого класса свой порог уверенности: модель вызывается с минимальным из них, чтобы не потерять мяч, а людей отсекаем по их собственному порогу. `detect_video` проверяет медленный тест в задаче 20.

**Файлы:**
- Создать: `src/aifootball/perception/detect.py`
- Тест: `tests/test_detect_rows.py`

- [ ] **Шаг 1. Тест `tests/test_detect_rows.py`**

```python
import math

import numpy as np

from aifootball.perception.detect import BALL, PERSON, boxes_to_rows

FRAME = np.zeros((100, 100, 3), dtype=np.uint8)


def _rows(classes, confs):
    xyxy = np.array([[10, 10, 30, 60]] * len(classes), dtype=np.float32)
    return boxes_to_rows(5, 0.5, FRAME, xyxy, np.array(classes), np.array(confs), 0.25, 0.10)


def test_each_class_has_own_threshold():
    rows = _rows([PERSON, PERSON, BALL, BALL], [0.9, 0.15, 0.15, 0.05])

    assert [(r["cls"], r["conf"]) for r in rows] == [("person", 0.9), ("ball", 0.15)]


def test_other_classes_dropped():
    assert _rows([2], [0.99]) == []  # 'car'


def test_person_gets_torso_color_ball_does_not():
    person, ball = _rows([PERSON, BALL], [0.9, 0.5])

    assert not math.isnan(person["torso_l"])
    assert math.isnan(ball["torso_l"])
    assert (person["frame_id"], person["ts"]) == (5, 0.5)
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_detect_rows.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.perception.detect'`

- [ ] **Шаг 3. Реализация `src/aifootball/perception/detect.py`**

```python
"""L1: детекция людей и мяча по видео -> detections.parquet."""

import math
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl
import torch

from aifootball import schemas
from aifootball.perception.color import NAN3, torso_lab
from aifootball.perception.frames import iter_frames
from aifootball.venue import Venue

PERSON = 0  # COCO 'person'
BALL = 32  # COCO 'sports ball'
CLASS_NAMES = {PERSON: "person", BALL: "ball"}


def pick_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def boxes_to_rows(
    frame_id: int,
    ts: float,
    frame: np.ndarray,
    xyxy: np.ndarray,
    classes: np.ndarray,
    confs: np.ndarray,
    conf_person: float,
    conf_ball: float,
) -> list[dict]:
    """Переводит выход детектора в строки detections.parquet.

    Порог у каждого класса свой: модель вызывается с минимальным из них,
    чтобы не потерять мяч, а людей отсекаем здесь по их собственному порогу.
    """
    thresholds = {PERSON: conf_person, BALL: conf_ball}
    rows = []
    for box, cls, conf in zip(xyxy, classes, confs):
        cls, conf = int(cls), float(conf)
        if cls not in CLASS_NAMES or conf < thresholds[cls]:
            continue
        l, a, b = torso_lab(frame, box) if cls == PERSON else NAN3
        x1, y1, x2, y2 = (float(v) for v in box)
        rows.append({
            "frame_id": frame_id, "ts": ts, "cls": CLASS_NAMES[cls],
            "x1": x1, "y1": y1, "x2": x2, "y2": y2, "conf": conf,
            "torso_l": l, "torso_a": a, "torso_b": b,
        })
    return rows


def detect_video(video: Path, venue: Venue, weights: Path, progress_every: int = 250) -> pl.DataFrame:
    if not weights.exists():
        raise FileNotFoundError(f"нет весов модели: {weights}")
    from ultralytics import YOLO  # тяжёлый импорт — только когда реально детектируем

    model = YOLO(str(weights))
    device = pick_device()
    conf = min(venue.conf_person, venue.conf_ball)
    rows: list[dict] = []
    started = time.perf_counter()

    for n, (frame_id, ts, frame) in enumerate(iter_frames(video, venue.target_fps), start=1):
        result = model.predict(
            frame, imgsz=venue.imgsz, device=device, classes=list(CLASS_NAMES), conf=conf, verbose=False
        )[0]
        boxes = result.boxes
        rows.extend(boxes_to_rows(
            frame_id, ts, frame,
            boxes.xyxy.cpu().numpy(), boxes.cls.cpu().numpy(), boxes.conf.cpu().numpy(),
            venue.conf_person, venue.conf_ball,
        ))
        if n % progress_every == 0:
            elapsed = time.perf_counter() - started
            print(f"  {n} кадров, {ts / 60:.1f} мин видео, {n / elapsed:.1f} кадр/с", file=sys.stderr)

    if not rows:
        return schemas.empty("detections")
    return pl.DataFrame(rows, schema=schemas.DETECTIONS)
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_detect_rows.py -v`

Ожидается: `3 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/perception/detect.py tests/test_detect_rows.py
git commit -m "Детекция людей и мяча в detections.parquet" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 10. Трекинг

ByteTrack из пакета `trackers`: `supervision.ByteTrack` устарел и удаляется в supervision 0.31. Библиотечный порог создания трека 0.7 снижен до 0.4 — иначе дальние игроки с уверенностью 0.3–0.6 не получат трек вовсе. Строки сопоставляются с треками через `data["row"]`: трекер меняет порядок детекций.

**Файлы:**
- Создать: `src/aifootball/perception/track.py`
- Тест: `tests/test_track.py`

- [ ] **Шаг 1. Тест `tests/test_track.py`**

```python
import polars as pl

from aifootball import schemas
from aifootball.perception.track import track_people


def _det(frame_id, x, y, conf=0.9, cls="person"):
    return {
        "frame_id": frame_id, "ts": frame_id / 10, "cls": cls,
        "x1": x, "y1": y, "x2": x + 20, "y2": y + 50, "conf": conf,
        "torso_l": 100.0, "torso_a": 150.0, "torso_b": 130.0,
    }


def _two_runners(n_frames=15, skip_second_at=None):
    rows = []
    for f in range(n_frames):
        rows.append(_det(f, 20 + 3 * f, 20))  # внутри поля 0..400 x 0..200
        if f != skip_second_at:
            rows.append(_det(f, 300 + 3 * f, 250))  # ноги на y=300 — за полем
    return pl.DataFrame(rows, schema=schemas.DETECTIONS)


def test_two_objects_get_two_stable_ids(venue):
    tracks = track_people(_two_runners(), venue)

    ids_per_frame = tracks.group_by("frame_id").agg(pl.col("track_id").n_unique())
    assert tracks["track_id"].n_unique() == 2
    # первый кадр трек ещё не подтверждён, дальше — оба объекта в каждом кадре
    assert ids_per_frame.filter(pl.col("frame_id") > 0)["track_id"].to_list() == [2] * 14


def test_id_survives_missed_frame(venue):
    tracks = track_people(_two_runners(skip_second_at=7), venue)

    assert tracks["track_id"].n_unique() == 2


def test_foot_point_and_pitch_flag(venue):
    tracks = track_people(_two_runners(), venue)
    row = tracks.filter(pl.col("frame_id") == 5).sort("x1")

    assert row["foot_x"].to_list() == [45.0, 325.0]  # центр нижней грани
    assert row["foot_y"].to_list() == [70.0, 300.0]
    assert row["in_pitch"].to_list() == [True, False]
    assert set(tracks["role"]) == {"unknown"}


def test_ball_rows_are_not_tracked(venue):
    rows = [_det(f, 20 + 3 * f, 20) for f in range(5)] + [_det(2, 100, 100, cls="ball")]
    tracks = track_people(pl.DataFrame(rows, schema=schemas.DETECTIONS), venue)

    assert set(tracks["cls"]) == {"person"}


def test_matches_tracks_schema(venue):
    tracks = track_people(_two_runners(), venue)
    assert set(tracks.columns) == set(schemas.TRACKS)
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_track.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.perception.track'`

- [ ] **Шаг 3. Реализация `src/aifootball/perception/track.py`**

```python
"""L1: трекинг людей по готовым детекциям -> tracks.parquet (без команд)."""

import numpy as np
import polars as pl
import supervision as sv
from trackers import ByteTrackTracker

from aifootball import schemas
from aifootball.geometry.polygons import points_in_polygon
from aifootball.venue import Venue

# Сколько держать потерянный трек. В trackers буфер задаётся в кадрах при 30 fps
# и сам пересчитывается под реальный fps: 90 = 3 секунды.
LOST_BUFFER_30FPS = 90
# Порог создания нового трека. Библиотечные 0.7 слишком строги: дальние игроки
# детектируются с уверенностью 0.3-0.6 и никогда бы не получили трек.
ACTIVATION_CONF = 0.4
HIGH_CONF = 0.5


def track_people(detections: pl.DataFrame, venue: Venue) -> pl.DataFrame:
    """Присваивает людям track_id, считает точку касания пола и флаг «на поле».

    Роль и команда здесь ещё не известны: role='unknown', team=null.
    Их заполняет perception.teams.assign_teams.
    """
    polygon = venue.require_polygon()
    people = detections.filter(pl.col("cls") == "person").sort("frame_id").with_row_index("row")
    if people.is_empty():
        return schemas.empty("tracks")

    tracker = ByteTrackTracker(
        lost_track_buffer=LOST_BUFFER_30FPS,
        frame_rate=venue.target_fps,
        track_activation_threshold=ACTIVATION_CONF,
        high_conf_det_threshold=HIGH_CONF,
        minimum_consecutive_frames=2,
    )
    by_frame = {key[0]: group for key, group in people.partition_by("frame_id", as_dict=True).items()}
    # Кадры берём из всех детекций, включая мяч: трекер должен «увидеть» каждый
    # обработанный кадр, иначе неправильно отсчитает время жизни потерянных треков.
    # Кадр, где не нашлось вообще ничего, сюда не попадёт — на футзале с
    # 10 игроками в кадре такого не бывает.
    frames = detections.select("frame_id", "ts").unique("frame_id").sort("frame_id")

    rows: list[int] = []
    track_ids: list[int] = []
    for frame_id, ts in frames.iter_rows():
        group = by_frame.get(frame_id)
        if group is None:
            tracked = tracker.update(sv.Detections.empty(), timestamp=ts)
        else:
            tracked = tracker.update(
                sv.Detections(
                    xyxy=group.select("x1", "y1", "x2", "y2").to_numpy().astype(np.float32),
                    confidence=group["conf"].to_numpy().astype(np.float32),
                    class_id=np.zeros(len(group), dtype=int),
                    data={"row": group["row"].to_numpy()},
                ),
                timestamp=ts,
            )
        if len(tracked) == 0:
            continue
        confirmed = tracked.tracker_id >= 0  # -1 — трек ещё не подтверждён
        rows.extend(tracked.data["row"][confirmed].tolist())
        track_ids.extend(tracked.tracker_id[confirmed].tolist())

    assigned = pl.DataFrame(
        {"row": rows, "track_id": track_ids}, schema={"row": pl.UInt32, "track_id": pl.Int32}
    )
    tracked_people = people.join(assigned, on="row", how="inner").drop("row")

    foot = np.column_stack([
        ((tracked_people["x1"] + tracked_people["x2"]) / 2).to_numpy(),
        tracked_people["y2"].to_numpy(),
    ])
    return tracked_people.with_columns(
        foot_x=pl.Series(foot[:, 0], dtype=pl.Float32),
        foot_y=pl.Series(foot[:, 1], dtype=pl.Float32),
        in_pitch=pl.Series(points_in_polygon(foot, polygon)),
        role=pl.lit("unknown"),
        team=pl.lit(None, dtype=pl.Utf8),
    ).sort("frame_id", "track_id")
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_track.py -v`

Ожидается: `5 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/perception/track.py tests/test_track.py
git commit -m "Трекинг людей через ByteTrack" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 11. Команды по цвету формы

k-means на 2 кластера по цветности (a, b) без яркости: освещение в зале неровное. Короткие треки и треки вне поля остаются `unknown`. Это базовая версия: вратари и судьи попадут в одну из команд, роли разделяются в фазе 3.

**Файлы:**
- Создать: `src/aifootball/perception/teams.py`
- Тест: `tests/test_teams.py`

- [ ] **Шаг 1. Тест `tests/test_teams.py`**

```python
import polars as pl

from aifootball import schemas
from aifootball.perception.teams import assign_teams


def _track(track_id, a, n, in_pitch=True):
    return [
        {
            "frame_id": f, "ts": f / 10, "cls": "person",
            "x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 30.0, "conf": 0.9,
            "torso_l": 120.0, "torso_a": a + (f % 3), "torso_b": 140.0,
            "track_id": track_id, "foot_x": 5.0, "foot_y": 30.0,
            "in_pitch": in_pitch, "role": "unknown", "team": None,
        }
        for f in range(n)
    ]


def _tracks(*groups):
    return pl.DataFrame([row for group in groups for row in group], schema=schemas.TRACKS)


def _team_of(result, track_id):
    return result.filter(pl.col("track_id") == track_id)["team"].unique().to_list()


def test_splits_red_and_green_into_two_teams():
    tracks = _tracks(
        _track(1, a=200, n=12), _track(2, a=195, n=15), _track(3, a=205, n=11),  # красные
        _track(4, a=60, n=12), _track(5, a=70, n=20),  # зелёные
    )

    result = assign_teams(tracks)

    assert _team_of(result, 4) == _team_of(result, 5) == ["A"]  # зеленее — «A»
    assert _team_of(result, 1) == _team_of(result, 2) == _team_of(result, 3) == ["B"]
    assert set(result["role"]) == {"player"}


def test_short_and_off_pitch_tracks_stay_unknown():
    tracks = _tracks(
        _track(1, a=200, n=12), _track(2, a=60, n=12),
        _track(3, a=200, n=4),  # слишком короткий
        _track(4, a=60, n=30, in_pitch=False),  # зритель на балконе
    )

    result = assign_teams(tracks)

    for track_id in (3, 4):
        rows = result.filter(pl.col("track_id") == track_id)
        assert rows["role"].unique().to_list() == ["unknown"]
        assert rows["team"].unique().to_list() == [None]


def test_not_enough_tracks_leaves_everyone_unknown():
    result = assign_teams(_tracks(_track(1, a=200, n=12)))

    assert result["role"].unique().to_list() == ["unknown"]


def test_keeps_tracks_schema():
    result = assign_teams(_tracks(_track(1, a=200, n=12), _track(2, a=60, n=12)))
    assert result.columns == list(schemas.TRACKS)
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_teams.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.perception.teams'`

- [ ] **Шаг 3. Реализация `src/aifootball/perception/teams.py`**

```python
"""Базовое деление треков на две команды по цвету формы.

Это заведомо простая версия для фазы 1: вратари и судьи попадут в одну из
двух команд. Роли разделяются в фазе 3, после замера качества на валидации.
"""

import cv2
import numpy as np
import polars as pl

# Трек участвует в кластеризации, только если он достаточно долго был на поле:
# по короткому обрывку цвет формы определяется ненадёжно.
MIN_OBSERVATIONS = 10


def assign_teams(tracks: pl.DataFrame) -> pl.DataFrame:
    """Заполняет role и team. Длинные треки на поле — player A/B, остальные — unknown."""
    per_track = (
        tracks.filter(pl.col("in_pitch") & pl.col("torso_a").is_not_nan())
        .group_by("track_id")
        .agg(
            n=pl.len(),
            a=pl.col("torso_a").median(),
            b=pl.col("torso_b").median(),
        )
        .filter(pl.col("n") >= MIN_OBSERVATIONS)
        .sort("track_id")
    )
    if len(per_track) < 2:
        return tracks.with_columns(role=pl.lit("unknown"), team=pl.lit(None, dtype=pl.Utf8))

    # Только a и b (цветность), без яркости L: освещение в зале неровное,
    # а цвет формы от него почти не зависит.
    features = per_track.select("a", "b").to_numpy().astype(np.float32)
    labels = _two_clusters(features)
    teams = pl.DataFrame(
        {"track_id": per_track["track_id"], "team_new": labels},
        schema={"track_id": pl.Int32, "team_new": pl.Utf8},
    )
    return (
        tracks.drop("role", "team")
        .join(teams, on="track_id", how="left")
        .rename({"team_new": "team"})
        .with_columns(
            role=pl.when(pl.col("team").is_null()).then(pl.lit("unknown")).otherwise(pl.lit("player"))
        )
        .select(tracks.columns)
    )


def _two_clusters(features: np.ndarray) -> list[str]:
    """k-means на 2 кластера. Имена стабильны: «A» — кластер с меньшим a (зеленее)."""
    cv2.setRNGSeed(0)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1)
    _, labels, centers = cv2.kmeans(features, 2, None, criteria, 5, cv2.KMEANS_PP_CENTERS)
    first = int(np.argmin(centers[:, 0]))
    return ["A" if label == first else "B" for label in labels.ravel()]
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_teams.py -v`

Ожидается: `4 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/perception/teams.py tests/test_teams.py
git commit -m "Базовое деление треков на команды по цвету" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 12. Сглаживание и скорости

Скользящая медиана убирает единичные выбросы детектора, скользящее среднее — дрожание бокса. Пропуски до 1 с заполняются линейно. После более длинного разрыва трек режется на куски, и расстояние через разрыв не считается. Фильтр Калмана — в фазе 4.

**Файлы:**
- Создать: `src/aifootball/state/smooth.py`
- Тест: `tests/test_smooth.py`

- [ ] **Шаг 1. Тест `tests/test_smooth.py`**

```python
import numpy as np
import polars as pl
import pytest

from aifootball import schemas
from aifootball.state.smooth import smooth_tracks


def _positions(ts, x, y=None, track_id=1):
    n = len(ts)
    return pl.DataFrame({
        "frame_id": (np.asarray(ts) * 25).round().astype(np.int32),
        "ts": np.asarray(ts, dtype=float),
        "track_id": [track_id] * n,
        "role": ["player"] * n,
        "team": ["A"] * n,
        "x_m": np.asarray(x, dtype=float),
        "y_m": np.zeros(n) if y is None else np.asarray(y, dtype=float),
    })


def _run(ts, x):
    """3 м/с вдоль x с частотой 10 Гц."""
    return smooth_tracks(_positions(ts, x))


def test_straight_run_keeps_speed_everywhere():
    ts = np.arange(30) / 10
    state = _run(ts, 3 * ts)

    assert state["speed"].to_numpy() == pytest.approx(np.full(30, 3.0), abs=1e-6)
    assert state["x_m"].to_numpy() == pytest.approx(3 * ts, abs=1e-6)
    assert state.schema == pl.Schema(schemas.STATE)


def test_single_detector_glitch_is_removed():
    ts = np.arange(30) / 10
    x = 3 * ts
    x[10] += 5.0  # детектор на один кадр «прыгнул» на 5 м

    assert _run(ts, x)["speed"].max() < 4.5


def test_short_gap_is_filled():
    ts = np.delete(np.arange(30) / 10, [11, 12, 13, 14])  # пропуск 0.5 с

    state = _run(ts, 3 * ts)

    assert len(state) == 30
    assert state["interpolated"].sum() == 4
    assert state["speed"].to_numpy() == pytest.approx(np.full(30, 3.0), abs=1e-6)


def test_long_gap_splits_track_instead_of_teleporting():
    before = np.arange(10) / 10
    after = np.arange(40, 50) / 10  # 3 секунды вне кадра
    ts = np.concatenate([before, after])
    x = np.concatenate([3 * before, 20 + 3 * after])  # вернулся в другом месте

    state = _run(ts, x)

    assert len(state) == 20 and state["interpolated"].sum() == 0
    assert state["speed"].max() == pytest.approx(3.0, abs=1e-6)


def test_single_point_track():
    state = _run([0.0], [5.0])

    assert state["speed"].to_list() == [0.0]


def test_empty_input():
    assert smooth_tracks(_positions([], []).clear()).is_empty()
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_smooth.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.state.smooth'`

- [ ] **Шаг 3. Реализация `src/aifootball/state/smooth.py`**

```python
"""Сглаживание траекторий, заполнение коротких пропусков и скорости.

Фаза 1 — простая и предсказуемая версия: скользящая медиана убирает единичные
выбросы детектора, скользящее среднее — дрожание бокса. Фильтр Калмана — в фазе 4.
"""

import numpy as np
import polars as pl
from numpy.lib.stride_tricks import sliding_window_view

from aifootball import schemas

# Пропуск короче этого заполняется линейно: игрок за секунду не исчезает.
# Длиннее — трек режется на куски, и дистанция через разрыв не считается.
MAX_GAP_S = 1.0
# Окно сглаживания в отсчётах: при 10 fps это полсекунды.
WINDOW = 5


def smooth_tracks(positions: pl.DataFrame) -> pl.DataFrame:
    """positions: frame_id, ts, track_id, role, team, x_m, y_m -> таблица схемы STATE."""
    if positions.is_empty():
        return schemas.empty("state")
    parts = [
        _smooth_track(group)
        for _, group in positions.sort("track_id", "ts").group_by("track_id", maintain_order=True)
    ]
    return pl.concat(parts).sort("frame_id", "track_id")


def _smooth_track(g: pl.DataFrame) -> pl.DataFrame:
    ts = g["ts"].to_numpy().astype(np.float64)
    x = g["x_m"].to_numpy().astype(np.float64)
    y = g["y_m"].to_numpy().astype(np.float64)
    frame_id = g["frame_id"].to_numpy().astype(np.int64)

    ts, x, y, frame_id, interpolated = _fill_short_gaps(ts, x, y, frame_id)

    xs, ys = x.copy(), y.copy()
    vx, vy = np.zeros_like(x), np.zeros_like(y)
    for seg in _segments(ts):
        xs[seg] = _rolling_mean(_rolling_median(x[seg]))
        ys[seg] = _rolling_mean(_rolling_median(y[seg]))
        vx[seg] = _velocity(xs[seg], ts[seg])
        vy[seg] = _velocity(ys[seg], ts[seg])

    n = len(ts)
    return pl.DataFrame(
        {
            "frame_id": frame_id,
            "ts": ts,
            "track_id": np.full(n, g["track_id"][0]),
            "role": [g["role"][0]] * n,
            "team": [g["team"][0]] * n,
            "x_m": xs,
            "y_m": ys,
            "vx": vx,
            "vy": vy,
            "speed": np.hypot(vx, vy),
            "interpolated": interpolated,
        },
        schema=schemas.STATE,
    )


def _fill_short_gaps(ts, x, y, frame_id):
    interpolated = np.zeros(len(ts), dtype=bool)
    if len(ts) < 2:
        return ts, x, y, frame_id, interpolated
    step = float(np.median(np.diff(ts)))
    out = {"ts": [ts[0]], "x": [x[0]], "y": [y[0]], "f": [frame_id[0]], "i": [False]}
    for i in range(1, len(ts)):
        dt = ts[i] - ts[i - 1]
        if 1.5 * step < dt <= MAX_GAP_S:
            missing = int(round(dt / step)) - 1
            for k in range(1, missing + 1):
                w = k / (missing + 1)
                out["ts"].append(ts[i - 1] + w * dt)
                out["x"].append(x[i - 1] + w * (x[i] - x[i - 1]))
                out["y"].append(y[i - 1] + w * (y[i] - y[i - 1]))
                out["f"].append(int(round(frame_id[i - 1] + w * (frame_id[i] - frame_id[i - 1]))))
                out["i"].append(True)
        out["ts"].append(ts[i])
        out["x"].append(x[i])
        out["y"].append(y[i])
        out["f"].append(frame_id[i])
        out["i"].append(False)
    return (
        np.array(out["ts"]), np.array(out["x"]), np.array(out["y"]),
        np.array(out["f"], dtype=np.int64), np.array(out["i"], dtype=bool),
    )


def _segments(ts: np.ndarray) -> list[slice]:
    """Куски трека без разрывов длиннее MAX_GAP_S."""
    cuts = np.flatnonzero(np.diff(ts) > MAX_GAP_S) + 1
    bounds = [0, *cuts.tolist(), len(ts)]
    return [slice(a, b) for a, b in zip(bounds[:-1], bounds[1:])]


def _pad(v: np.ndarray) -> np.ndarray:
    # «Нечётное» отражение сохраняет линейный тренд на краях: иначе края
    # траектории тянутся к первой точке и скорость на них занижается.
    return np.pad(v, WINDOW // 2, mode="reflect", reflect_type="odd")


def _rolling_median(v: np.ndarray) -> np.ndarray:
    if len(v) < WINDOW:
        return v.copy()
    return np.median(sliding_window_view(_pad(v), WINDOW), axis=1)


def _rolling_mean(v: np.ndarray) -> np.ndarray:
    if len(v) < WINDOW:
        return v.copy()
    return sliding_window_view(_pad(v), WINDOW).mean(axis=1)


def _velocity(v: np.ndarray, ts: np.ndarray) -> np.ndarray:
    if len(v) < 2:
        return np.zeros_like(v)
    return np.gradient(v, ts)
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_smooth.py -v`

Ожидается: `6 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/state/smooth.py tests/test_smooth.py
git commit -m "Сглаживание траекторий и скорости" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 13. Проекция в метры

L2: только точки на поле, снятие дисторсии, гомография, сглаживание.

**Файлы:**
- Создать: `src/aifootball/state/project.py`
- Тест: `tests/test_project.py`

- [ ] **Шаг 1. Тест `tests/test_project.py`**

```python
import polars as pl
import pytest

from aifootball import schemas
from aifootball.state.project import project_tracks


def _track_rows(n=10):
    rows = []
    for f in range(n):
        base = {
            "frame_id": f, "ts": f / 10, "cls": "person",
            "x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 0.0, "conf": 0.9,
            "torso_l": 0.0, "torso_a": 0.0, "torso_b": 0.0,
            "role": "player", "team": "A",
        }
        rows.append({**base, "track_id": 1, "foot_x": 100.0 + 10 * f, "foot_y": 50.0, "in_pitch": True})
        rows.append({**base, "track_id": 2, "foot_x": 300.0, "foot_y": 900.0, "in_pitch": False})
    return pl.DataFrame(rows, schema=schemas.TRACKS)


def test_projects_pixels_to_meters(venue):
    state = project_tracks(_track_rows(), venue)  # 10 px = 1 м

    assert state["track_id"].unique().to_list() == [1]  # трек вне поля отброшен
    assert state["x_m"].to_list() == pytest.approx([10.0 + f for f in range(10)], abs=1e-4)
    assert state["y_m"].to_list() == pytest.approx([5.0] * 10, abs=1e-4)
    assert state["speed"].to_list() == pytest.approx([10.0] * 10, abs=1e-3)  # 1 м за 0.1 с


def test_nothing_on_pitch_gives_empty_state(venue):
    tracks = _track_rows().filter(pl.col("track_id") == 2)
    assert project_tracks(tracks, venue).is_empty()
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_project.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.state.project'`

- [ ] **Шаг 3. Реализация `src/aifootball/state/project.py`**

```python
"""L2: tracks.parquet -> state.parquet (позиции на поле в метрах)."""

import polars as pl

from aifootball import schemas
from aifootball.geometry.homography import apply_homography
from aifootball.geometry.undistort import undistort_points
from aifootball.state.smooth import smooth_tracks
from aifootball.venue import Venue


def project_tracks(tracks: pl.DataFrame, venue: Venue) -> pl.DataFrame:
    """Берёт только точки на поле, переводит пиксели в метры и сглаживает."""
    H = venue.require_homography()
    on_pitch = tracks.filter(pl.col("in_pitch"))
    if on_pitch.is_empty():
        return schemas.empty("state")

    pixels = on_pitch.select("foot_x", "foot_y").to_numpy()
    meters = apply_homography(H, undistort_points(pixels, venue.calib))
    positions = on_pitch.select("frame_id", "ts", "track_id", "role", "team").with_columns(
        x_m=pl.Series(meters[:, 0]),
        y_m=pl.Series(meters[:, 1]),
    )
    return smooth_tracks(positions)
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_project.py -v`

Ожидается: `2 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/state/project.py tests/test_project.py
git commit -m "Проекция треков в метры на поле" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 14. Метрики

L3: у каждой метрики есть `observed_s` — сколько секунд объект реально был на поле. Тепловая карта — сетка 1×1 м, значения в секундах.

**Файлы:**
- Создать: `src/aifootball/analytics/metrics.py`
- Тест: `tests/test_metrics.py`

- [ ] **Шаг 1. Тест `tests/test_metrics.py`**

```python
import numpy as np
import polars as pl
import pytest

from aifootball import schemas
from aifootball.analytics.metrics import compute_metrics


def _state(track_id, team, ts, x, y=5.0, speed=1.0):
    n = len(ts)
    return pl.DataFrame({
        "frame_id": (np.asarray(ts) * 25).round().astype(np.int32),
        "ts": np.asarray(ts, dtype=float),
        "track_id": [track_id] * n, "role": ["player"] * n, "team": [team] * n,
        "x_m": np.asarray(x, dtype=float), "y_m": np.full(n, y),
        "vx": np.full(n, speed), "vy": np.zeros(n), "speed": np.full(n, speed),
        "interpolated": [False] * n,
    }, schema=schemas.STATE)


def _metrics():
    ts = np.arange(101) / 10  # 10 секунд, 1 м/с вдоль x
    gap_ts = np.concatenate([np.arange(21) / 10, 7 + np.arange(21) / 10])  # 5 секунд вне кадра
    state = pl.concat([
        _state(1, "A", ts, 5 + ts),
        _state(2, "A", gap_ts, 5 + gap_ts),
    ])
    return compute_metrics(state, 40.0, 20.0)


def test_track_distance_and_observed_time():
    track = _metrics()["tracks"]["1"]

    assert track["distance_m"] == pytest.approx(10.0)
    assert track["observed_s"] == pytest.approx(10.0)
    assert track["distance_per_min"] == pytest.approx(60.0)
    assert track["max_speed_ms"] == pytest.approx(1.0)


def test_long_gap_not_counted():
    track = _metrics()["tracks"]["2"]

    assert track["observed_s"] == pytest.approx(4.0)
    assert track["distance_m"] == pytest.approx(4.0)


def test_team_totals_and_heatmap():
    teams = _metrics()["teams"]
    heat = np.array(teams["A"]["heatmap_s"])

    assert teams["A"]["tracks"] == ["1", "2"]
    assert teams["A"]["distance_m"] == pytest.approx(14.0)
    assert heat.shape == (40, 20)
    assert heat.sum() == pytest.approx((101 + 42) * 0.1)
    assert heat[:, 5].sum() == pytest.approx(heat.sum())  # все бегали по y=5
    assert teams["B"] == {"tracks": [], "observed_s": 0, "distance_m": 0, "heatmap_s": np.zeros((40, 20)).tolist()}
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_metrics.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.analytics.metrics'`

- [ ] **Шаг 3. Реализация `src/aifootball/analytics/metrics.py`**

```python
"""L3: state.parquet -> metrics.json.

Каждая метрика идёт вместе с observed_s — сколько секунд объект реально был
виден на поле. Без этого дистанция игрока, ушедшего из кадра, молча занижается.
"""

import math

import numpy as np
import polars as pl

from aifootball import schemas
from aifootball.state.smooth import MAX_GAP_S

HEATMAP_CELL_M = 1.0
TEAMS = ("A", "B")


def compute_metrics(state: pl.DataFrame, length_m: float, width_m: float) -> dict:
    tracks = {
        str(track_id): _track_metrics(group)
        for (track_id,), group in state.sort("track_id", "ts").group_by("track_id", maintain_order=True)
    }
    sample_s = _sampling_step(state)
    teams = {}
    for team in TEAMS:
        members = sorted((tid for tid, m in tracks.items() if m["team"] == team), key=int)
        team_state = state.filter(pl.col("team") == team)
        teams[team] = {
            "tracks": members,
            "observed_s": round(sum(tracks[t]["observed_s"] for t in members), 2),
            "distance_m": round(sum(tracks[t]["distance_m"] for t in members), 2),
            # heatmap_s[ix][iy] — секунды, проведённые игроками команды в клетке 1x1 м
            "heatmap_s": _heatmap(team_state, length_m, width_m, sample_s),
        }
    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "pitch": {"length_m": length_m, "width_m": width_m, "heatmap_cell_m": HEATMAP_CELL_M},
        "teams": teams,
        "tracks": tracks,
    }


def _track_metrics(g: pl.DataFrame) -> dict:
    ts = g["ts"].to_numpy()
    x, y = g["x_m"].to_numpy(), g["y_m"].to_numpy()
    dt = np.diff(ts)
    steps = np.hypot(np.diff(x), np.diff(y))
    continuous = dt <= MAX_GAP_S  # через длинный разрыв расстояние не считаем
    observed = float(dt[continuous].sum())
    distance = float(steps[continuous].sum())
    return {
        "team": g["team"][0],
        "role": g["role"][0],
        "observed_s": round(observed, 2),
        "distance_m": round(distance, 2),
        "distance_per_min": round(distance / observed * 60, 1) if observed > 0 else 0.0,
        "max_speed_ms": round(float(g["speed"].max()), 2),
    }


def _sampling_step(state: pl.DataFrame) -> float:
    """Шаг между отсчётами внутри трека (при 10 fps — 0.1 с)."""
    diffs = (
        state.sort("track_id", "ts")
        .select(pl.col("ts").diff().over("track_id").alias("dt"))
        .filter(pl.col("dt") > 0)["dt"]
    )
    return float(diffs.median()) if len(diffs) else 0.0


def _heatmap(team_state: pl.DataFrame, length_m: float, width_m: float, sample_s: float) -> list:
    nx = math.ceil(length_m / HEATMAP_CELL_M)
    ny = math.ceil(width_m / HEATMAP_CELL_M)
    if team_state.is_empty():
        return np.zeros((nx, ny)).tolist()
    hist, _, _ = np.histogram2d(
        team_state["x_m"].to_numpy(),
        team_state["y_m"].to_numpy(),
        bins=[nx, ny],
        range=[[0, length_m], [0, width_m]],
    )
    return (hist * sample_s).round(2).tolist()
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_metrics.py -v`

Ожидается: `3 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/analytics/metrics.py tests/test_metrics.py
git commit -m "Метрики: дистанция, покрытие, тепловые карты" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 15. Критерии готовности фазы 1

Автоматическая проверка двух критериев из спеки: скорость не выше 10 м/с, не меньше 95% точек внутри поля.

**Файлы:**
- Создать: `src/aifootball/analytics/checks.py`
- Тест: `tests/test_checks.py`

- [ ] **Шаг 1. Тест `tests/test_checks.py`**

```python
import numpy as np
import polars as pl

from aifootball import schemas
from aifootball.analytics.checks import phase1_checks


def _state(x, speed):
    n = len(x)
    return pl.DataFrame({
        "frame_id": np.arange(n, dtype=np.int32), "ts": np.arange(n) / 10,
        "track_id": np.arange(n, dtype=np.int32) % 2, "role": ["player"] * n, "team": ["A"] * n,
        "x_m": np.asarray(x, float), "y_m": np.full(n, 10.0),
        "vx": np.asarray(speed, float), "vy": np.zeros(n), "speed": np.asarray(speed, float),
        "interpolated": [False] * n,
    }, schema=schemas.STATE)


def test_plausible_state_passes():
    result = phase1_checks(_state(x=np.linspace(0, 40, 100), speed=np.full(100, 5.0)), 40, 20)
    assert result["passed"] and result["inside_share"] == 1.0


def test_too_fast_fails():
    speed = np.full(100, 5.0)
    speed[42] = 14.0
    result = phase1_checks(_state(x=np.full(100, 20.0), speed=speed), 40, 20)

    assert not result["passed"] and not result["speed_ok"]
    assert result["fastest_track"] == 0


def test_points_outside_pitch_fail():
    x = np.full(100, 20.0)
    x[:10] = 45.0  # 10% точек за лицевой линией
    result = phase1_checks(_state(x=x, speed=np.full(100, 5.0)), 40, 20)

    assert not result["inside_ok"] and result["inside_share"] == 0.9


def test_empty_state_fails():
    assert phase1_checks(schemas.empty("state"), 40, 20)["passed"] is False
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_checks.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.analytics.checks'`

- [ ] **Шаг 3. Реализация `src/aifootball/analytics/checks.py`**

```python
"""Критерии готовности фазы 1 — считаются по state.parquet."""

import polars as pl

MAX_SPEED_MS = 10.0  # быстрее футзалист не бегает; больше — значит, врёт трекинг или гомография
MIN_INSIDE_SHARE = 0.95
EDGE_TOLERANCE_M = 0.5  # игрок на линии поля — не вылет


def phase1_checks(state: pl.DataFrame, length_m: float, width_m: float) -> dict:
    if state.is_empty():
        return {"passed": False, "reason": "state пуст"}
    observed = state.filter(~pl.col("interpolated"))
    tol = EDGE_TOLERANCE_M
    inside = observed.filter(
        pl.col("x_m").is_between(-tol, length_m + tol) & pl.col("y_m").is_between(-tol, width_m + tol)
    )
    inside_share = len(inside) / len(observed) if len(observed) else 0.0
    max_speed = float(state["speed"].max())
    speed_ok = max_speed <= MAX_SPEED_MS
    inside_ok = inside_share >= MIN_INSIDE_SHARE
    return {
        "passed": speed_ok and inside_ok,
        "max_speed_ms": round(max_speed, 2),
        "speed_ok": speed_ok,
        "inside_share": round(inside_share, 4),
        "inside_ok": inside_ok,
        "fastest_track": int(state.sort("speed")["track_id"][-1]),
    }
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_checks.py -v`

Ожидается: `4 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/analytics/checks.py tests/test_checks.py
git commit -m "Автоматические критерии фазы 1" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 16. Схема поля сверху и боксы на кадре

Дальняя боковая линия на схеме — сверху, как на кадре.

**Файлы:**
- Создать: `src/aifootball/viz/topdown.py`
- Создать: `src/aifootball/viz/overlay.py`
- Тест: `tests/test_topdown_overlay.py`

- [ ] **Шаг 1. Тест `tests/test_topdown_overlay.py`**

```python
import numpy as np

from aifootball.viz.overlay import draw_tracks
from aifootball.viz.topdown import LINE_BGR, TEAM_BGR, canvas_size, draw_pitch, draw_players, to_canvas


def test_canvas_geometry():
    assert canvas_size(40, 20) == (880, 480)
    assert to_canvas(0, 0, 20) == (40, 440)  # ближний левый угол — внизу слева
    assert to_canvas(40, 20, 20) == (840, 40)  # дальний правый — вверху справа


def test_pitch_lines_drawn():
    img = draw_pitch(40, 20)
    u, v = to_canvas(10, 0, 20)  # середина ближней боковой линии

    assert img.shape == (480, 880, 3)
    assert tuple(int(c) for c in img[v, u]) == LINE_BGR


def test_player_drawn_in_team_color_on_copy():
    pitch = draw_pitch(40, 20)
    img = draw_players(pitch, [{"x_m": 10.0, "y_m": 10.0, "team": "A", "track_id": 3}], 20)
    u, v = to_canvas(10, 10, 20)

    assert tuple(int(c) for c in img[v, u]) == TEAM_BGR["A"]
    assert not np.array_equal(img, pitch)


def test_overlay_does_not_touch_input():
    frame = np.zeros((100, 100, 3), np.uint8)
    row = {"x1": 10, "y1": 10, "x2": 40, "y2": 80, "in_pitch": True, "team": "B", "track_id": 1}

    img = draw_tracks(frame, [row])

    assert frame.sum() == 0
    assert tuple(int(c) for c in img[40, 10]) == TEAM_BGR["B"]  # левая грань бокса
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_topdown_overlay.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.viz.overlay'`

- [ ] **Шаг 3. Реализация `src/aifootball/viz/topdown.py`**

```python
"""Схема поля сверху и игроки на ней."""

import cv2
import numpy as np

PX_PER_M = 20
MARGIN_M = 2.0
FLOOR_BGR = (55, 55, 55)
LINE_BGR = (235, 235, 235)
TEAM_BGR = {"A": (80, 200, 80), "B": (200, 90, 230)}
UNKNOWN_BGR = (160, 160, 160)
CENTER_CIRCLE_R_M = 3.0
GOAL_WIDTH_M = 3.0
GOAL_DEPTH_M = 1.0


def canvas_size(length_m: float, width_m: float) -> tuple[int, int]:
    """(ширина, высота) холста в пикселях."""
    return (
        int(round((length_m + 2 * MARGIN_M) * PX_PER_M)),
        int(round((width_m + 2 * MARGIN_M) * PX_PER_M)),
    )


def meters_to_canvas(width_m: float) -> np.ndarray:
    """Матрица 3x3: метры поля -> пиксели холста. Дальняя боковая линия — сверху."""
    return np.array([
        [PX_PER_M, 0.0, MARGIN_M * PX_PER_M],
        [0.0, -PX_PER_M, (MARGIN_M + width_m) * PX_PER_M],
        [0.0, 0.0, 1.0],
    ])


def to_canvas(x_m: float, y_m: float, width_m: float) -> tuple[int, int]:
    u, v, _ = meters_to_canvas(width_m) @ np.array([x_m, y_m, 1.0])
    return int(round(u)), int(round(v))


def draw_pitch(length_m: float, width_m: float) -> np.ndarray:
    w, h = canvas_size(length_m, width_m)
    img = np.full((h, w, 3), FLOOR_BGR, dtype=np.uint8)
    L, W = length_m, width_m
    cv2.rectangle(img, to_canvas(0, W, W), to_canvas(L, 0, W), LINE_BGR, 2)
    cv2.line(img, to_canvas(L / 2, 0, W), to_canvas(L / 2, W, W), LINE_BGR, 2)
    cv2.circle(img, to_canvas(L / 2, W / 2, W), int(CENTER_CIRCLE_R_M * PX_PER_M), LINE_BGR, 2)
    half = GOAL_WIDTH_M / 2
    for goal_x, outward in ((0.0, -GOAL_DEPTH_M), (L, GOAL_DEPTH_M)):
        cv2.rectangle(
            img,
            to_canvas(goal_x, W / 2 + half, W),
            to_canvas(goal_x + outward, W / 2 - half, W),
            LINE_BGR,
            2,
        )
    return img


def draw_players(pitch: np.ndarray, rows, width_m: float) -> np.ndarray:
    """rows — словари с x_m, y_m, team, track_id. Рисует на копии."""
    img = pitch.copy()
    for row in rows:
        center = to_canvas(row["x_m"], row["y_m"], width_m)
        color = TEAM_BGR.get(row["team"], UNKNOWN_BGR)
        cv2.circle(img, center, int(0.45 * PX_PER_M), color, -1)
        cv2.putText(
            img, str(row["track_id"]), (center[0] + 10, center[1] - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, LINE_BGR, 1, cv2.LINE_AA,
        )
    return img
```

- [ ] **Шаг 4. Реализация `src/aifootball/viz/overlay.py`**

```python
"""Боксы треков поверх исходного кадра."""

import cv2
import numpy as np

from aifootball.viz.topdown import TEAM_BGR, UNKNOWN_BGR

POLYGON_BGR = (0, 220, 255)
OFF_PITCH_BGR = (110, 110, 110)


def draw_tracks(frame: np.ndarray, rows, polygon: np.ndarray | None = None) -> np.ndarray:
    """rows — словари из tracks.parquet. Кто вне поля — тонкой серой рамкой."""
    img = frame.copy()
    if polygon is not None:
        cv2.polylines(img, [np.asarray(polygon, np.int32).reshape(-1, 1, 2)], True, POLYGON_BGR, 1)
    for row in rows:
        p1 = (int(row["x1"]), int(row["y1"]))
        p2 = (int(row["x2"]), int(row["y2"]))
        if row["in_pitch"]:
            color, thickness = TEAM_BGR.get(row["team"], UNKNOWN_BGR), 2
        else:
            color, thickness = OFF_PITCH_BGR, 1
        cv2.rectangle(img, p1, p2, color, thickness)
        cv2.putText(
            img, str(row["track_id"]), (p1[0], max(p1[1] - 4, 10)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA,
        )
    return img
```

- [ ] **Шаг 5. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_topdown_overlay.py -v`

Ожидается: `4 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 6. Коммит**

```bash
git add src/aifootball/viz/topdown.py src/aifootball/viz/overlay.py tests/test_topdown_overlay.py
git commit -m "Схема поля сверху и боксы треков на кадре" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 17. Отладочное видео

Главный инструмент отладки фазы: исходный кадр и схема сверху, синхронно.

**Файлы:**
- Создать: `src/aifootball/viz/debug_video.py`
- Тест: `tests/test_debug_video.py`

- [ ] **Шаг 1. Тест `tests/test_debug_video.py`**

```python
import cv2
import polars as pl

from aifootball import schemas
from aifootball.viz.debug_video import render_debug_video


def test_debug_video_written(tiny_video, venue, tmp_path):
    tracks = pl.DataFrame([{
        "frame_id": 0, "ts": 0.0, "cls": "person", "x1": 10.0, "y1": 10.0, "x2": 40.0, "y2": 80.0,
        "conf": 0.9, "torso_l": 0.0, "torso_a": 0.0, "torso_b": 0.0, "track_id": 1,
        "foot_x": 25.0, "foot_y": 80.0, "in_pitch": True, "role": "player", "team": "A",
    }], schema=schemas.TRACKS)
    state = pl.DataFrame([{
        "frame_id": 0, "ts": 0.0, "track_id": 1, "role": "player", "team": "A",
        "x_m": 2.5, "y_m": 8.0, "vx": 0.0, "vy": 0.0, "speed": 0.0, "interpolated": False,
    }], schema=schemas.STATE)
    out = tmp_path / "debug.mp4"

    written = render_debug_video(tiny_video, tracks, state, venue, out, max_seconds=1.0)

    cap = cv2.VideoCapture(str(out))
    assert written == 11  # 0.0 .. 1.0 с при 10 fps
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 11
    cap.release()
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_debug_video.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.viz.debug_video'`

- [ ] **Шаг 3. Реализация `src/aifootball/viz/debug_video.py`**

```python
"""Главный инструмент отладки: исходный кадр и схема сверху, синхронно."""

from pathlib import Path

import cv2
import numpy as np
import polars as pl

from aifootball.perception.frames import iter_frames
from aifootball.venue import Venue
from aifootball.viz.overlay import draw_tracks
from aifootball.viz.topdown import draw_pitch, draw_players


def render_debug_video(
    video: Path,
    tracks: pl.DataFrame,
    state: pl.DataFrame,
    venue: Venue,
    out_path: Path,
    max_seconds: float | None = None,
) -> int:
    """Пишет mp4 «кадр | вид сверху». Возвращает число записанных кадров."""
    tracks_by_frame = _by_frame(tracks)
    state_by_frame = _by_frame(state)
    pitch = draw_pitch(venue.length_m, venue.width_m)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    writer = None
    written = 0
    try:
        for frame_id, ts, frame in iter_frames(video, venue.target_fps):
            if max_seconds is not None and ts > max_seconds:
                break
            left = draw_tracks(frame, tracks_by_frame.get(frame_id, []), venue.pitch_polygon_px)
            right = draw_players(pitch, state_by_frame.get(frame_id, []), venue.width_m)
            right = _fit_height(right, left.shape[0])
            canvas = np.hstack([left, right])
            cv2.putText(
                canvas, f"t={ts:7.2f}s  frame={frame_id}", (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA,
            )
            if writer is None:
                height, width = canvas.shape[:2]
                writer = cv2.VideoWriter(
                    str(out_path), cv2.VideoWriter.fourcc(*"mp4v"), venue.target_fps, (width, height)
                )
            writer.write(canvas)
            written += 1
    finally:
        if writer is not None:
            writer.release()
    return written


def _by_frame(df: pl.DataFrame) -> dict[int, list[dict]]:
    if df.is_empty():
        return {}
    return {key[0]: group.to_dicts() for key, group in df.partition_by("frame_id", as_dict=True).items()}


def _fit_height(img: np.ndarray, height: int) -> np.ndarray:
    scale = height / img.shape[0]
    return cv2.resize(img, (int(round(img.shape[1] * scale)), height))
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_debug_video.py -v`

Ожидается: `1 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/viz/debug_video.py tests/test_debug_video.py
git commit -m "Отладочное видео: кадр и вид сверху" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 18. Инструмент разметки

Сохранение разметки и проверочный вид сверху тестируются. Окно для кликов (`mark_points.py`) тестами не покрыто, проверяется руками в задаче 21. Координаты точек хранятся как кликнуты, в сырых пикселях. Гомография считается по ним после снятия дисторсии.

**Файлы:**
- Создать: `src/aifootball/tools/marking.py`
- Создать: `src/aifootball/tools/mark_points.py`
- Тест: `tests/test_marking.py`

- [ ] **Шаг 1. Тест `tests/test_marking.py`**

```python
import numpy as np
import pytest

from aifootball.geometry.homography import apply_homography
from aifootball.tools.marking import save_homography, save_polygon, topdown_preview
from aifootball.venue import load_venue
from conftest import make_venue_dir

PIXELS = [[100, 400], [1100, 420], [900, 250], [300, 240], [640, 330]]
TRUE_H = np.array([[0.05, 0.01, -3.0], [0.002, 0.08, -10.0], [0.0001, 0.0009, 1.0]])


def test_polygon_saved_and_loaded(tmp_path):
    root = make_venue_dir(tmp_path / "v")

    save_polygon(root, [(0, 0), (10, 0), (10, 10)])

    assert load_venue(root).pitch_polygon_px.tolist() == [[0, 0], [10, 0], [10, 10]]


def test_polygon_needs_three_points(tmp_path):
    with pytest.raises(ValueError, match="минимум 3"):
        save_polygon(make_venue_dir(tmp_path / "v"), [(0, 0), (1, 1)])


def test_homography_saved_with_honest_error(tmp_path):
    root = make_venue_dir(tmp_path / "v")
    meters = apply_homography(TRUE_H, np.array(PIXELS, float))

    info = save_homography(root, PIXELS, meters, calib=None)

    assert info["reprojection_error_m"] < 1e-3
    assert info["leave_one_out_error_m"] < 1e-3
    np.testing.assert_allclose(apply_homography(load_venue(root).H, np.array(PIXELS, float)), meters, atol=1e-4)


def test_preview_has_canvas_size():
    frame = np.full((720, 1280, 3), 90, np.uint8)
    scale = np.array([[0.1, 0, 0], [0, 0.1, 0], [0, 0, 1.0]])

    assert topdown_preview(frame, scale, 40, 20).shape == (480, 880, 3)
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_marking.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.tools.marking'`

- [ ] **Шаг 3. Реализация `src/aifootball/tools/marking.py`**

```python
"""Сохранение разметки установки и проверочная картинка «вид сверху»."""

import json
from pathlib import Path

import cv2
import numpy as np

from aifootball.geometry.homography import fit_homography, leave_one_out_error
from aifootball.geometry.undistort import undistort_points
from aifootball.venue import Calibration
from aifootball.viz.topdown import LINE_BGR, canvas_size, draw_pitch, meters_to_canvas


def save_polygon(venue_root: Path, points_px) -> Path:
    points = np.asarray(points_px, dtype=float).reshape(-1, 2)
    if len(points) < 3:
        raise ValueError(f"у контура поля нужно минимум 3 вершины, дано {len(points)}")
    path = venue_root / "pitch_polygon.json"
    path.write_text(json.dumps({"points_px": points.round(1).tolist()}, indent=2), encoding="utf-8")
    return path


def save_homography(venue_root: Path, points_px, points_m, calib: Calibration | None) -> dict:
    """Считает H по кликнутым точкам и сохраняет. Точки хранятся как кликнуты — в сырых пикселях."""
    px = np.asarray(points_px, dtype=float).reshape(-1, 2)
    m = np.asarray(points_m, dtype=float).reshape(-1, 2)
    undistorted = undistort_points(px, calib)
    H, error = fit_homography(undistorted, m)
    loo = leave_one_out_error(undistorted, m) if len(px) > 4 else None
    data = {
        "H": H.tolist(),
        "points": [{"px": p.tolist(), "m": q.tolist()} for p, q in zip(px, m)],
        "reprojection_error_m": round(error, 3),
        "leave_one_out_error_m": None if loo is None else round(loo, 3),
    }
    (venue_root / "homography.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def topdown_preview(
    frame: np.ndarray, H: np.ndarray, length_m: float, width_m: float, calib: Calibration | None = None
) -> np.ndarray:
    """Кадр, «развёрнутый» гомографией в вид сверху, с линиями поля поверх.

    Если H верна, линии на полу кадра лягут на нарисованные линии поля.
    """
    if calib is not None:
        frame = cv2.undistort(frame, calib.K, calib.dist)
    warp = meters_to_canvas(width_m) @ H
    warped = cv2.warpPerspective(frame, warp, canvas_size(length_m, width_m))
    lines = draw_pitch(length_m, width_m)
    mask = np.all(lines == LINE_BGR, axis=2)
    warped[mask] = LINE_BGR
    return warped
```

- [ ] **Шаг 4. Реализация `src/aifootball/tools/mark_points.py`**

```python
"""Ручная разметка установки камеры: контур поля и точки для гомографии.

    python -m aifootball.tools.mark_points polygon    --video V --venue DIR [--at 5] [--scale 1]
    python -m aifootball.tools.mark_points homography --video V --venue DIR [--at 5] [--scale 1]

Мышь: левый клик — поставить точку. Клавиши: Backspace — убрать последнюю,
Enter — сохранить, Esc — выйти без сохранения.
В режиме homography после каждого клика терминал спросит координаты точки в метрах.
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from aifootball.tools.marking import save_homography, save_polygon, topdown_preview
from aifootball.venue import load_venue

KEY_ENTER = {10, 13}
KEY_BACKSPACE = {8, 127}
KEY_ESC = 27
WINDOW = "mark_points"


def read_frame(video: Path, at_seconds: float) -> np.ndarray:
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, at_seconds * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        sys.exit(f"не удалось прочитать кадр {at_seconds} с из {video}")
    return frame


def collect_points(frame: np.ndarray, scale: float, ask_meters: bool):
    """Цикл кликов. Возвращает (пиксели, метры) или None, если нажали Esc."""
    pixels: list[tuple[float, float]] = []
    meters: list[tuple[float, float]] = []

    def on_mouse(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        point = (x / scale, y / scale)
        if ask_meters:
            answer = input(f"точка {len(pixels) + 1} ({point[0]:.0f}, {point[1]:.0f}) px — метры 'x y': ")
            try:
                xm, ym = (float(v) for v in answer.replace(",", " ").split())
            except ValueError:
                print("  не понял, точка не добавлена")
                return
            meters.append((xm, ym))
        pixels.append(point)

    cv2.namedWindow(WINDOW)
    cv2.setMouseCallback(WINDOW, on_mouse)
    while True:
        shown = cv2.resize(frame, None, fx=scale, fy=scale) if scale != 1 else frame.copy()
        for i, (x, y) in enumerate(pixels):
            p = (int(x * scale), int(y * scale))
            cv2.circle(shown, p, 5, (0, 0, 255), -1)
            cv2.putText(shown, str(i + 1), (p[0] + 6, p[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        if not ask_meters and len(pixels) > 1:
            poly = (np.array(pixels) * scale).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(shown, [poly], True, (0, 220, 255), 2)
        cv2.imshow(WINDOW, shown)
        key = cv2.waitKey(30) & 0xFF
        if key == KEY_ESC:
            cv2.destroyAllWindows()
            return None
        if key in KEY_BACKSPACE and pixels:
            pixels.pop()
            if ask_meters:
                meters.pop()
        if key in KEY_ENTER:
            cv2.destroyAllWindows()
            return pixels, meters


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["polygon", "homography"])
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--venue", type=Path, required=True)
    parser.add_argument("--at", type=float, default=5.0, help="секунда видео, с которой брать кадр")
    parser.add_argument("--scale", type=float, default=1.0, help="масштаб окна, если кадр не влезает в экран")
    args = parser.parse_args(argv)

    venue = load_venue(args.venue)
    frame = read_frame(args.video, args.at)
    collected = collect_points(frame, args.scale, ask_meters=args.mode == "homography")
    if collected is None:
        print("выход без сохранения")
        return
    pixels, meters = collected

    if args.mode == "polygon":
        path = save_polygon(args.venue, pixels)
        print(f"сохранено {len(pixels)} вершин -> {path}")
        return

    info = save_homography(args.venue, pixels, meters, venue.calib)
    print(f"точек: {len(pixels)}")
    print(f"ошибка на своих точках: {info['reprojection_error_m']} м")
    print(f"ошибка без каждой точки (честная): {info['leave_one_out_error_m']} м")
    preview = topdown_preview(frame, load_venue(args.venue).H, venue.length_m, venue.width_m, venue.calib)
    cv2.imshow("topdown preview — любая клавиша", preview)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
```

- [ ] **Шаг 5. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_marking.py -v`

Ожидается: `4 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 6. Коммит**

```bash
git add src/aifootball/tools/marking.py src/aifootball/tools/mark_points.py tests/test_marking.py
git commit -m "Инструмент разметки контура поля и гомографии" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 19. CLI пайплайна

Подкоманда на каждый шаг плюс `run`. `run` пропускает детекцию, если `detections.parquet` уже есть, поэтому итерации по трекингу и метрикам занимают секунды. `check` возвращает код 1, если критерии не выполнены. Интеграционный тест прогоняет все шаги после детекции на синтетических данных.

**Файлы:**
- Создать: `src/aifootball/cli.py`
- Тест: `tests/test_cli.py`

- [ ] **Шаг 1. Тест `tests/test_cli.py`**

```python
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
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Запуск: `.venv/bin/python -m pytest tests/test_cli.py -v`

Ожидается: ошибка сбора теста `ModuleNotFoundError: No module named 'aifootball.cli'`

- [ ] **Шаг 3. Реализация `src/aifootball/cli.py`**

```python
"""Пайплайн по шагам. Каждый шаг читает артефакт предыдущего из каталога матча.

    python -m aifootball.cli run     --video V --venue DIR --match DIR   # всё подряд
    python -m aifootball.cli detect  --video V --venue DIR --match DIR   # минуты
    python -m aifootball.cli track   --venue DIR --match DIR             # секунды
    python -m aifootball.cli project --venue DIR --match DIR
    python -m aifootball.cli metrics --venue DIR --match DIR
    python -m aifootball.cli check   --venue DIR --match DIR
    python -m aifootball.cli render  --video V --venue DIR --match DIR [--seconds 60]
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from aifootball import schemas
from aifootball.analytics.checks import phase1_checks
from aifootball.analytics.metrics import compute_metrics
from aifootball.perception.frames import video_fps
from aifootball.perception.teams import assign_teams
from aifootball.perception.track import track_people
from aifootball.state.project import project_tracks
from aifootball.venue import load_venue


def cmd_detect(args, venue) -> None:
    from aifootball.perception.detect import detect_video  # тянет torch — только здесь

    started = time.perf_counter()
    detections = detect_video(args.video, venue, args.models / venue.model)
    schemas.write(detections, args.match / "detections.parquet", "detections")
    schemas.write_json(
        {
            "video": str(args.video),
            "venue_id": venue.venue_id,
            "src_fps": video_fps(args.video),
            "target_fps": venue.target_fps,
            "model": venue.model,
            "imgsz": venue.imgsz,
            "schema_version": schemas.SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        args.match / "meta.json",
    )
    people = detections.filter(detections["cls"] == "person")
    print(
        f"detect: {detections['frame_id'].n_unique()} кадров, {len(people)} людей, "
        f"{len(detections) - len(people)} мячей за {time.perf_counter() - started:.0f} с"
    )


def cmd_track(args, venue) -> None:
    detections = schemas.read(args.match / "detections.parquet", "detections")
    tracks = assign_teams(track_people(detections, venue))
    schemas.write(tracks, args.match / "tracks.parquet", "tracks")
    on_pitch = tracks.filter(tracks["in_pitch"])
    print(
        f"track: {tracks['track_id'].n_unique()} треков, на поле {on_pitch['track_id'].n_unique()}, "
        f"команды {tracks.group_by('team').len().sort('team').rows()}"
    )


def cmd_project(args, venue) -> None:
    tracks = schemas.read(args.match / "tracks.parquet", "tracks")
    state = project_tracks(tracks, venue)
    schemas.write(state, args.match / "state.parquet", "state")
    print(f"project: {len(state)} позиций, из них восстановлено {int(state['interpolated'].sum())}")


def cmd_metrics(args, venue) -> None:
    state = schemas.read(args.match / "state.parquet", "state")
    metrics = compute_metrics(state, venue.length_m, venue.width_m)
    schemas.write_json(metrics, args.match / "metrics.json")
    for team, m in metrics["teams"].items():
        print(f"metrics: команда {team}: {m['distance_m']:.0f} м за {m['observed_s']:.0f} с наблюдения")


def cmd_check(args, venue) -> bool:
    state = schemas.read(args.match / "state.parquet", "state")
    result = phase1_checks(state, venue.length_m, venue.width_m)
    schemas.write_json(result, args.match / "checks.json")
    print("check:", json.dumps(result, ensure_ascii=False))
    return result["passed"]


def cmd_render(args, venue) -> None:
    from aifootball.viz.debug_video import render_debug_video

    tracks = schemas.read(args.match / "tracks.parquet", "tracks")
    state = schemas.read(args.match / "state.parquet", "state")
    out = args.match / "debug.mp4"
    written = render_debug_video(args.video, tracks, state, venue, out, max_seconds=args.seconds)
    print(f"render: {written} кадров -> {out}")


def cmd_run(args, venue) -> bool:
    if args.redetect or not (args.match / "detections.parquet").exists():
        cmd_detect(args, venue)
    else:
        print("detect: пропущен, detections.parquet уже есть (--redetect, чтобы пересчитать)")
    cmd_track(args, venue)
    cmd_project(args, venue)
    cmd_metrics(args, venue)
    passed = cmd_check(args, venue)
    cmd_render(args, venue)
    return passed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, video=False, models=False, seconds=False):
        p = sub.add_parser(name)
        p.add_argument("--venue", type=Path, required=True)
        p.add_argument("--match", type=Path, required=True)
        if video:
            p.add_argument("--video", type=Path, required=True)
        if models:
            p.add_argument("--models", type=Path, default=Path("models"))
        if seconds:
            p.add_argument("--seconds", type=float, default=None, help="отрисовать только начало")
        return p

    add("detect", video=True, models=True)
    add("track")
    add("project")
    add("metrics")
    add("check")
    add("render", video=True, seconds=True)
    run = add("run", video=True, models=True, seconds=True)
    run.add_argument("--redetect", action="store_true")
    return parser


COMMANDS = {
    "detect": cmd_detect, "track": cmd_track, "project": cmd_project, "metrics": cmd_metrics,
    "check": cmd_check, "render": cmd_render, "run": cmd_run,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    venue = load_venue(args.venue)
    result = COMMANDS[args.command](args, venue)
    return 1 if result is False else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Шаг 4. Тест зелёный**

Запуск: `.venv/bin/python -m pytest tests/test_cli.py -v`

Ожидается: `1 passed`. Затем весь набор: `.venv/bin/python -m pytest -q` — всё зелёное.

- [ ] **Шаг 5. Коммит**

```bash
git add src/aifootball/cli.py tests/test_cli.py
git commit -m "CLI: подкоманды пайплайна и run" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 20. Конфиг Костромы и медленный тест на настоящем видео

`venue.yaml` для полигона. Размеры поля 40×20 м — **допущение**: стандартная площадка, реальные размеры зала неизвестны. Медленный тест прогоняет YOLO по 10 секундам настоящего матча и ловит поломки, которые на синтетике не видны: формат выхода ultralytics, работу MPS, чтение h264.

**Файлы:**
- Создать: `configs/venues/kostroma/venue.yaml`
- Тест: `tests/test_real_video.py`

- [ ] **Шаг 1. `configs/venues/kostroma/venue.yaml`**

```yaml
# Кострома, YouTube x-ITNQMFm0M — полигон для разработки, не целевая установка.
# Размеры поля — ДОПУЩЕНИЕ: стандартная площадка 40x20 м. Проверяется в задаче 21.
venue_id: kostroma
pitch:
  length_m: 40.0
  width_m: 20.0
processing:
  target_fps: 10
  model: yolo11m.pt
  imgsz: 1280
  conf_person: 0.25
  conf_ball: 0.10
```

- [ ] **Шаг 2. Тест `tests/test_real_video.py`**

```python
"""Прогон на настоящем видео: YOLO на MPS, минуты. Запуск: pytest -m slow"""

import shutil
import subprocess
from pathlib import Path

import polars as pl
import pytest

from aifootball import schemas
from aifootball.perception.detect import detect_video
from aifootball.venue import load_venue

REPO = Path(__file__).resolve().parents[1]
FRAGMENT = REPO / "data/raw/kostroma_futsal_x-ITNQMFm0M_115-415.mp4"
MODELS = REPO / "models"
VENUE = REPO / "configs/venues/kostroma"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not FRAGMENT.exists(), reason="нет фрагмента видео в data/raw"),
    pytest.mark.skipif(not (MODELS / "yolo11m.pt").exists(), reason="нет весов в models/"),
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="нет ffmpeg"),
]


def test_detection_on_ten_seconds_of_real_match(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(FRAGMENT), "-t", "10", "-c", "copy", str(clip)], check=True)
    venue = load_venue(VENUE)

    detections = detect_video(clip, venue, MODELS / venue.model)

    per_frame = detections.filter(pl.col("cls") == "person").group_by("frame_id").len()["len"]
    # 10 с при 10 fps; «-c copy» режет по ключевым кадрам, поэтому ±1 кадр
    assert abs(detections["frame_id"].n_unique() - 100) <= 1
    assert 8 <= per_frame.median() <= 60  # игроки плюс зрители на балконе
    assert detections.schema == pl.Schema(schemas.DETECTIONS)
```

- [ ] **Шаг 3. Прогон**

Запуск: `.venv/bin/python -m pytest -m slow tests/test_real_video.py -v`

Ожидается: `1 passed` примерно за 15 секунд. Если вместо этого `skipped`, в причине написано, чего не хватает: фрагмента в `data/raw/`, весов в `models/` или `ffmpeg`.

Обычный `.venv/bin/python -m pytest -q` этот тест пропускает: `60 passed, 1 deselected`.

- [ ] **Шаг 4. Коммит**

```bash
git add configs/venues/kostroma/venue.yaml tests/test_real_video.py
git commit -m "Конфиг Костромы и медленный тест на настоящем видео" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 21. Разметка Костромы — ВРУЧНУЮ

**Выполняет человек.** Инструменту нужны клики мышью, агент это сделать не может. Займёт минут 15–20.

**Соглашение о координатах** (спека, раздел 4.1): метры, начало — ближний к камере левый угол поля. На кадрах Костромы:
- `x = 0` — лицевая линия у **ближних** ворот (внизу слева, в кадр не попадают), `x = 40` — у **дальних** ворот (видны справа у дальней стены);
- `y = 0` — боковая линия со стороны камеры, `y = 20` — дальняя боковая, вдоль стены с балконом.

- [ ] **Шаг 1. Контур поля**

```bash
.venv/bin/python -m aifootball.tools.mark_points polygon --video data/raw/kostroma_futsal_x-ITNQMFm0M_115-415.mp4 --venue configs/venues/kostroma --at 5
```

Кликами обведите **пол, где могут быть игроки**: ниже стены с балконом, без занавеса справа. Строго по линиям разметки не нужно — задача отсечь балкон, стены и зрителей. Enter — сохранить, Backspace — убрать последнюю точку.

Ожидается: `сохранено N вершин -> configs/venues/kostroma/pitch_polygon.json`.

- [ ] **Шаг 2. Точки для гомографии**

```bash
.venv/bin/python -m aifootball.tools.mark_points homography --video data/raw/kostroma_futsal_x-ITNQMFm0M_115-415.mp4 --venue configs/venues/kostroma --at 5
```

Поставьте **5–8 точек на полу**, разнесённых по видимой части поля. После каждого клика терминал спросит координаты в метрах: `x y`.

Кандидаты (при допущении 40×20 и воротах шириной 3 м):
- основания стоек дальних ворот: `40 8.5` и `40 11.5`;
- пересечение дальней лицевой и дальней боковой линий: `40 20`;
- пересечение средней линии с дальней боковой: `20 20`.

**Берите только точки, в координатах которых уверены.** Линии зала многослойные — гандбол, баскетбол, волейбол. Одна точка, взятая с чужой разметки, испортит всю гомографию.

Ожидается вывод:
```
точек: N
ошибка на своих точках: ... м
ошибка без каждой точки (честная): ... м
```
После вывода откроется окно предпросмотра: кадр, развёрнутый в вид сверху, с нарисованными линиями поля.

- [ ] **Шаг 3. Проверка качества разметки**

Разметка годится, если:
1. **честная ошибка меньше 1.0 м.** Для целевой камеры в Ф0 порог 0.5 м, но здесь размеры поля — допущение, и требовать больше нельзя;
2. **в предпросмотре линии пола на кадре ложатся на нарисованные линии поля** хотя бы на видимой половине.

Если не так — перезапустите шаг 2 и уберите сомнительные точки. Честная ошибка покажет, какая точка портит результат.

- [ ] **Шаг 4. Коммит**

```bash
git add configs/venues/kostroma/pitch_polygon.json configs/venues/kostroma/homography.json
git commit -m "Разметка поля и гомография Костромы" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 22. Прогон фрагмента и приёмка фазы 1

- [ ] **Шаг 1. Полный прогон**

```bash
.venv/bin/python -m aifootball.cli run --video data/raw/kostroma_futsal_x-ITNQMFm0M_115-415.mp4 --venue configs/venues/kostroma --match data/matches/kostroma-115-415 --seconds 60
```

Ожидается, около 5 минут (детекция 3000 кадров при ~11 кадр/с):
```
detect: 3000 кадров, ... людей, ... мячей за ... с
track: ... треков, на поле ..., команды [...]
project: ... позиций, из них восстановлено ...
metrics: команда A: ... м за ... с наблюдения
metrics: команда B: ... м за ... с наблюдения
check: {"passed": ..., ...}
render: 601 кадров -> data/matches/kostroma-115-415/debug.mp4
```

Повторный `run` детекцию пропускает, остальные шаги занимают секунды. Так и итерируются трекинг и метрики.

- [ ] **Шаг 2. Посмотреть отладочное видео**

```bash
open data/matches/kostroma-115-415/debug.mp4
```

На что смотреть:
- боксы игроков окрашены в цвет команды, зрители на балконе — не окрашены (вне контура);
- точки на схеме справа движутся вслед за игроками слева, без скачков через всё поле;
- вратари и судьи попадают в одну из команд — **в фазе 1 это ожидаемо**, роли разделяются в Ф3.

- [ ] **Шаг 3. Критерии готовности (спека, Ф1)**

| Критерий | Где смотреть | Порог |
|---|---|---|
| Весь фрагмент проходит одной командой | шаг 1 | без ошибок |
| Собирается отладочное видео | `data/matches/kostroma-115-415/debug.mp4` | есть, открывается |
| Скорость после сглаживания | `checks.json` → `max_speed_ms` | ≤ 10 м/с |
| Точки игроков внутри поля | `checks.json` → `inside_share` | ≥ 0.95 |

**Если критерий не выполнен, это результат, а не повод крутить пороги.** Найдите в отладочном видео трек из `fastest_track` и посмотрите, что с ним происходит. Типичные причины:
- гомография: точки уезжают за поле на дальней половине — вернуться к задаче 21;
- переключение ID: трек перескакивает с одного игрока на другого — это работа фазы 3, зафиксировать как исходное число.

- [ ] **Шаг 4. Записать результат в `docs/phase1-results.md`**

Создать файл и заполнить цифрами из вывода шага 1, `checks.json` и `metrics.json`:

```markdown
# Фаза 1 — результаты прогона

**Дата:** ГГГГ-ММ-ДД
**Фрагмент:** Кострома, 1:55–6:55 (300 с), yolo11m @ 1280, 10 fps

## Время
- детекция: ... с на 300 с видео → оценка на матч 45 мин: ... мин

## Трекинг
- треков всего / на поле: ... / ...
- строк по командам A / B / без команды: ... / ... / ...

## Критерии
- max_speed_ms: ... (порог 10) — пройден / не пройден
- inside_share: ... (порог 0.95) — пройден / не пройден
- честная ошибка гомографии: ... м

## Что видно в отладочном видео
- ...

## Что это значит для фазы 2–3
- ...
```

Главное число для следующих фаз — **треков на поле за 5 минут**. Игроков в кадре около 12, и всё, что сверх этого, — обрывы и переключения ID. Это исходная точка, которую фаза 3 должна уменьшить.

- [ ] **Шаг 5. Коммит**

```bash
git add docs/phase1-results.md
git commit -m "Результаты фазы 1 на фрагменте Костромы" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## После фазы 1

- **Фаза 2** получает отдельный план. Предразметка для CVAT строится из `tracks.parquet` этой фазы, а метрики качества считаются через `trackers.eval` — он уже стоит в зависимостях.
- Числа из `docs/phase1-results.md` становятся точкой отсчёта для критериев фазы 3.
