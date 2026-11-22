"""Конфиг установки камеры: всё, что зависит от конкретного зала и точки съёмки.

Каталог установки `configs/venues/<venue_id>/`:
  venue.yaml          — размеры поля и параметры обработки (пишется руками)
  pitch_polygon.json  — контур поля на кадре (размечается инструментом mark_points)
  homography.json     — пиксели -> метры (размечается инструментом mark_points)
  calib.json          — дисторсия объектива (необязательно)
  reference.jpg       — эталонный кадр камеры (для поворотной камеры обязателен)
  replay_badge.png    — образец плашки повтора трансляции (необязательно)

Поворотная камера (трансляция с оператором: пан, наклон, зум) — секция camera в venue.yaml:
  camera:
    motion: ptz                    # fixed (по умолчанию) | ptz
    overlay: [[0, 0, 1, 0.16]]     # графика трансляции: доли кадра x1, y1, x2, y2
    replay_badge_xy: [1590, 900]   # где на кадре левый верхний угол плашки повтора
Гомография и контур тогда относятся к эталонному кадру: каждый кадр записи привязывается к нему
(geometry.registration), контур поля считается по гомографии и размерам поля.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import yaml

CAMERA_MOTIONS = ('fixed', 'ptz')
# Запас контура поля поворотной камеры за линиями: игрок у бровки чуть заступает, а скамейка
# на ВШЭ стоит в метре от линии и в контур попадать не должна.
PTZ_PITCH_MARGIN_M = 0.3


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
    # Мяч: своя дообученная модель (путь внутри каталога моделей) вместо общей COCO,
    # размер вырезки в полном разрешении и запас за контуром поля — ауты и игра у борта.
    ball_model: str | None = None
    ball_tile: int = 1280
    ball_margin_px: int = 0
    frame_width: int | None = None
    frame_height: int | None = None
    camera_profile_id: str | None = None
    camera_motion: str = 'fixed'
    overlay: tuple[tuple[float, float, float, float], ...] = ()
    replay_badge: np.ndarray | None = None  # образец плашки повтора, оттенки серого
    replay_badge_xy: tuple[int, int] | None = None

    @property
    def is_ptz(self) -> bool:
        return self.camera_motion == 'ptz'

    def require_polygon(self) -> np.ndarray:
        if self.pitch_polygon_px is None:
            raise FileNotFoundError(
                f'{self.root / "pitch_polygon.json"}: контур поля не размечен. '
                f'Запустите: python -m aifootball.tools.mark_points polygon ...'
            )
        return self.pitch_polygon_px

    def require_homography(self) -> np.ndarray:
        if self.H is None:
            raise FileNotFoundError(
                f'{self.root / "homography.json"}: гомография не размечена. '
                f'Запустите: python -m aifootball.tools.mark_points homography ...'
            )
        return self.H


def load_venue(root: Path) -> Venue:
    cfg = yaml.safe_load((root / 'venue.yaml').read_text(encoding='utf-8'))
    pitch = cfg['pitch']
    proc = cfg['processing']
    camera = cfg.get('camera') or {}
    motion = camera.get('motion', 'fixed')
    if motion not in CAMERA_MOTIONS:
        raise ValueError(f'{root / "venue.yaml"}: camera.motion должен быть одним из {CAMERA_MOTIONS}')
    overlay = tuple(tuple(float(v) for v in rect) for rect in camera.get('overlay') or ())
    if any(len(r) != 4 or not (0 <= r[0] < r[2] <= 1 and 0 <= r[1] < r[3] <= 1) for r in overlay):
        raise ValueError(f'{root / "venue.yaml"}: camera.overlay — прямоугольники в долях кадра x1, y1, x2, y2')
    badge_xy = camera.get('replay_badge_xy')
    badge = None
    if badge_xy is not None:
        badge = cv2.imread(str(root / 'replay_badge.png'), cv2.IMREAD_GRAYSCALE)
        if badge is None:
            raise FileNotFoundError(f'{root / "replay_badge.png"}: нет образца плашки повтора')
        badge_xy = (int(badge_xy[0]), int(badge_xy[1]))
    venue = Venue(
        root=root,
        venue_id=cfg['venue_id'],
        length_m=float(pitch['length_m']),
        width_m=float(pitch['width_m']),
        target_fps=float(proc['target_fps']),
        model=proc['model'],
        imgsz=int(proc['imgsz']),
        conf_person=float(proc['conf_person']),
        conf_ball=float(proc['conf_ball']),
        pitch_polygon_px=_load_polygon(root / 'pitch_polygon.json'),
        H=_load_homography(root / 'homography.json'),
        calib=_load_calibration(root / 'calib.json'),
        lost_buffer_30fps=int(proc.get('lost_buffer_30fps', 90)),
        min_team_observations=int(proc.get('min_team_observations', 10)),
        max_gap_s=float(proc.get('max_gap_s', 1.0)),
        max_physical_speed=float(proc.get('max_physical_speed', 10.0)),
        ball_model=proc.get('ball_model'),
        ball_tile=int(proc.get('ball_tile', 1280)),
        ball_margin_px=int(proc.get('ball_margin_px', 0)),
        frame_width=int(proc['frame_width']) if proc.get('frame_width') else None,
        frame_height=int(proc['frame_height']) if proc.get('frame_height') else None,
        camera_profile_id=proc.get('camera_profile_id'),
        camera_motion=motion,
        overlay=overlay,
        replay_badge=badge,
        replay_badge_xy=badge_xy,
    )
    if not venue.is_ptz:
        return venue
    if venue.frame_width is None or venue.frame_height is None:
        raise ValueError(f'{root / "venue.yaml"}: для поворотной камеры укажите processing.frame_width и frame_height')
    if venue.calib is not None:
        # Зум меняет дисторсию: одна модель объектива на все кадры не годится, а сверка поворотов её не учитывает.
        raise ValueError(f'{root}: поворотная камера без calib.json — модель объектива не поддерживается')
    H = venue.require_homography()
    from dataclasses import replace

    polygon = pitch_polygon_from_homography(H, venue.length_m, venue.width_m, PTZ_PITCH_MARGIN_M)
    return replace(venue, pitch_polygon_px=polygon)


def pitch_polygon_from_homography(H: np.ndarray, length_m: float, width_m: float, margin_m: float) -> np.ndarray:
    """Контур поля (с запасом) в пикселях кадра гомографии «пиксели -> метры». Может выходить за кадр."""
    m = margin_m
    corners = np.array([[-m, -m], [length_m + m, -m], [length_m + m, width_m + m], [-m, width_m + m]])
    p = np.linalg.inv(H) @ np.vstack([corners.T, np.ones(4)])
    if not (np.all(p[2] > 1e-12) or np.all(p[2] < -1e-12)):
        raise ValueError('Поле не целиком перед эталонным кадром: гомография поворотной камеры неверна')
    return (p[:2] / p[2]).T.astype(np.float32)


def _load_polygon(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    points = json.loads(path.read_text(encoding='utf-8'))['points_px']
    return np.asarray(points, dtype=np.float32)


def _load_homography(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    return np.asarray(json.loads(path.read_text(encoding='utf-8'))['H'], dtype=np.float64)


def _load_calibration(path: Path) -> Calibration | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding='utf-8'))
    return Calibration(
        K=np.asarray(data['K'], dtype=np.float64),
        dist=np.asarray(data['dist'], dtype=np.float64),
    )
