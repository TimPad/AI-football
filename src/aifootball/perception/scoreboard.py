"""Голы с табло трансляции без OCR: смена картинки цифр на плашках счёта.

Плашки счёта (слева и справа) задаются шаблоном оформления трансляции в пикселях кадра. Цифры не
распознаются: гол — это новое устойчивое изображение на плашке, которого раньше не было. Поэтому
считается число голов и время смены, а итог сверяется со счётом протокола уже на сайте.

Замер на трансляции «Мяч ТВ» (ВШЭ, 15.11.2026): 15 из 15 голов, итог 12:3 как в протоколе; шум между
соседними кадрами p99 0.0043 доли пикселей маски, порог 0.012. Табло меняют за 1–3 с до повтора, то есть
позже самого гола (до ~15 с).
"""

import json
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

FPS = 2  # кадров плашки в секунду
THRESHOLD = 0.012  # доля пикселей маски цифр, при которой картинка считается другой
PERSIST_S = 3.0  # новое состояние должно продержаться столько секунд
REPLAY_PAD_S = 2.0  # вокруг повторов плашка не читается: переходы и старый счёт
VISIBLE = (0.005, 0.6)  # доля «цифры» в маске; вне — плашки нет в кадре


@dataclass(frozen=True)
class Overlay:
    """Шаблон оформления трансляции: плашки счёта (x, y, ширина, высота) в кадре размера frame."""

    name: str
    frame: tuple[int, int]
    left: tuple[int, int, int, int]
    right: tuple[int, int, int, int]
    digits: str = 'dark'  # тёмные цифры на светлой плашке или 'light'

    def scaled(self, size: tuple[int, int]) -> 'Overlay':
        sx, sy = size[0] / self.frame[0], size[1] / self.frame[1]

        def box(b):
            return (round(b[0] * sx), round(b[1] * sy), round(b[2] * sx), round(b[3] * sy))

        return replace(self, frame=tuple(size), left=box(self.left), right=box(self.right))


def load_overlay(path: Path) -> Overlay:
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    boxes = {side: tuple(int(v) for v in raw[side]) for side in ('left', 'right')}
    if any(len(b) != 4 or b[2] <= 0 or b[3] <= 0 for b in boxes.values()):
        raise ValueError(f'Неверные плашки счёта в {path}')
    digits = raw.get('digits', 'dark')
    if digits not in ('dark', 'light'):
        raise ValueError(f'digits: dark или light, а не {digits}')
    return Overlay(str(raw['name']), tuple(int(v) for v in raw['frame']), boxes['left'], boxes['right'], digits)


def read_plates(video: Path, overlay: Overlay, size: tuple[int, int], fps: int = FPS) -> dict[str, np.ndarray]:
    """Серые кадры обеих плашек с частотой fps: {'left': (N, h, w), 'right': ...}."""
    o = overlay.scaled(size)
    x0 = min(o.left[0], o.right[0])
    y0 = min(o.left[1], o.right[1])
    x1 = max(o.left[0] + o.left[2], o.right[0] + o.right[2])
    y1 = max(o.left[1] + o.left[3], o.right[1] + o.right[3])
    w, h = x1 - x0, y1 - y0
    # Серый до обрезки: у yuv420 crop округляет нечётные размеры и сдвиги до чётных.
    command = ['ffmpeg', '-v', 'error', '-i', str(video), '-vf', f'fps={fps},format=gray,crop={w}:{h}:{x0}:{y0}']
    command += ['-f', 'rawvideo', '-pix_fmt', 'gray', '-']
    raw = subprocess.run(command, capture_output=True, check=True).stdout
    band = np.frombuffer(raw, np.uint8).reshape(-1, h, w)
    return {
        side: band[:, b[1] - y0 : b[1] - y0 + b[3], b[0] - x0 : b[0] - x0 + b[2]]
        for side, b in (('left', o.left), ('right', o.right))
    }


def plate_changes(frames: np.ndarray, fps: float, replays, digits: str = 'dark') -> list[float]:
    """Времена голов одной плашки, с: момент сразу после последнего кадра со старым счётом."""
    masks = frames < 128 if digits == 'dark' else frames >= 128

    def differ(a, b):
        return (a != b).mean() > THRESHOLD

    def hidden(t, m):
        share = m.mean()
        return not VISIBLE[0] <= share <= VISIBLE[1] or any(
            a - REPLAY_PAD_S <= t <= b + REPLAY_PAD_S for a, b in replays
        )

    seen, out = [], []
    current = candidate = None
    last_current = 0
    count = 0
    for i, m in enumerate(masks):
        if hidden(i / fps, m):
            candidate, count = None, 0
            continue
        if current is not None and not differ(m, current):
            last_current, candidate, count = i, None, 0
            continue
        if candidate is not None and not differ(m, candidate):
            count += 1
        else:
            candidate, count = m, 1
        if count >= PERSIST_S * fps:
            # Счёт, который уже был (оператор снял и вернул гол), — не новый гол.
            if not any(not differ(s, candidate) for s in seen):
                seen.append(candidate)
                if current is not None:
                    out.append(round((last_current + 1) / fps, 2))
            current, last_current, candidate, count = candidate, i, None, 0
    return out


def board_goals(changes: dict[str, list[float]], spans) -> dict:
    """Голы обеих плашек по времени: тайм и время от его начала по интервалам таймов на видео."""
    starts = [a for a, _ in spans]
    goals = []
    for side, times in changes.items():
        for t in times:
            k = max([i for i, a in enumerate(starts) if a <= t] or [0])
            a, b = spans[k]
            elapsed = min(max(0.0, t - a), b - a)
            goals.append({'t_s': float(t), 'side': side, 'period': k + 1, 'elapsed_s': round(elapsed, 1)})
    goals.sort(key=lambda g: (g['t_s'], g['side']))
    return {'final': {side: len(times) for side, times in changes.items()}, 'goals': goals}


def scoreboard_from_video(video: Path, overlay: Overlay, size: tuple[int, int], replays, spans) -> dict:
    """Блок scoreboard отчёта: шаблон, итог по плашкам и голы с таймом и временем от его начала."""
    plates = read_plates(video, overlay, size)
    changes = {side: plate_changes(frames, FPS, replays, overlay.digits) for side, frames in plates.items()}
    return {'source': 'broadcast', 'overlay': overlay.name, **board_goals(changes, spans)}
