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
    lost_buffer_30fps: int = 90
    min_team_observations: int = 10
    max_gap_s: float = 1.0
    max_physical_speed: float = 10.0

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
        lost_buffer_30fps=int(proc.get("lost_buffer_30fps", 90)),
        min_team_observations=int(proc.get("min_team_observations", 10)),
        max_gap_s=float(proc.get("max_gap_s", 1.0)),
        max_physical_speed=float(proc.get("max_physical_speed", 10.0)),
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
