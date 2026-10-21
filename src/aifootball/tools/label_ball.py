"""Эталонная разметка мяча на кадрах, которые видит детектор.

    python -m aifootball.tools.label_ball --video V --venue DIR --out data/gt/<матч>/ball.parquet [--count 200] [--scale 1]
        [--frames кадры.txt]   — вместо равномерной выборки: номера кадров, по одному в строке
        [--hints догадки.parquet] — догадки модели (frame_id, x, y): жёлтый круг на неразмеченном кадре

Мышь: левый клик — центр мяча (по лупе в углу удобнее целиться).
Клавиши (не зависят от раскладки):
    1          мяча нет в кадре (вне обзора камеры, ушёл за поле)
    2          мяч в кадре, но не видно (закрыт игроком, не разобрать)
    пробел     проиграть соседние кадры, чтобы найти мяч по движению; ещё раз — стоп
    Enter      на неразмеченном кадре с жёлтым кругом — принять догадку модели; иначе следующий кадр без изменений
    Backspace  предыдущий кадр
    Esc        выйти (всё уже сохранено)
Каждая метка сохраняется сразу; повторный запуск продолжает с первого неразмеченного кадра.
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from aifootball.tools.ball_labels import BallLabels, load_hints, point_on_enter, render_view, sampled_frame_ids, spread
from aifootball.venue import load_venue

KEY_ESC = 27
KEY_ENTER = {10, 13}
KEY_BACKSPACE = {8, 127}
KEY_SPACE = 32
KEY_ABSENT = ord("1")
KEY_HIDDEN = ord("2")
CONTEXT = 8  # соседних кадров исходного видео с каждой стороны: ±0.32 с при 25 fps
PLAY_DELAY_MS = 90
TARGET_BGR = (0, 200, 0)
CONTEXT_BGR = (0, 140, 255)
WINDOW = "label_ball"


class Clip:
    """Кадр для разметки и его соседи; последний прочитанный держим в памяти."""

    def __init__(self, video: Path):
        self.cap = cv2.VideoCapture(str(video))
        if not self.cap.isOpened():
            sys.exit(f"не открывается видео: {video}")
        self.total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self._cached: tuple[int, list[tuple[int, np.ndarray]]] | None = None

    def around(self, frame_id: int) -> list[tuple[int, np.ndarray]]:
        if self._cached is None or self._cached[0] != frame_id:
            start = max(0, frame_id - CONTEXT)
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, start)
            frames = []
            for offset in range(start - frame_id, CONTEXT + 1):
                ok, frame = self.cap.read()
                if not ok:
                    break
                frames.append((offset, frame))
            self._cached = (frame_id, frames)
        return self._cached[1]

    def target(self, frame_id: int) -> np.ndarray:
        return next(frame for offset, frame in self.around(frame_id) if offset == 0)


def run(clip: Clip, labels: BallLabels, frame_ids: list[int], scale: float,
        hints: dict[int, tuple[float, float]] | None = None) -> None:
    hints = hints or {}
    idx = labels.first_unlabeled(frame_ids)
    if idx == len(frame_ids):
        print("все кадры уже размечены — открываю с начала для проверки")
        idx = 0
    ui = {"cursor": None, "click": None}

    def on_mouse(event, x, y, flags, param):
        ui["cursor"] = (int(x / scale), int(y / scale))
        if event == cv2.EVENT_LBUTTONDOWN:
            ui["click"] = (x / scale, y / scale)

    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW, on_mouse)
    playing, play_pos = False, 0
    while idx < len(frame_ids):
        frame_id = frame_ids[idx]
        c = labels.counts()
        header = f"{idx + 1}/{len(frame_ids)}  frame {frame_id}  ball {c['visible']} none {c['absent']} hidden {c['hidden']}"
        if playing:
            context = clip.around(frame_id)
            offset, frame = context[play_pos % len(context)]
            play_pos += 1
            shown = render_view(frame, scale, None, ui["cursor"], f"{header}  PLAY {offset:+d}",
                                border_bgr=TARGET_BGR if offset == 0 else CONTEXT_BGR)
        else:
            shown = render_view(clip.target(frame_id), scale, labels.get(frame_id), ui["cursor"], header,
                                border_bgr=TARGET_BGR, hint=hints.get(frame_id))
        cv2.imshow(WINDOW, shown)
        key = cv2.waitKey(PLAY_DELAY_MS if playing else 30) & 0xFF

        if ui["click"] is not None:
            point, ui["click"] = ui["click"], None
            if playing:
                playing = False  # клик во время проигрывания только останавливает: метка ставится на свой кадр
                continue
            labels.set(frame_id, "visible", point)
            idx += 1
        elif key == KEY_ESC:
            break
        elif key == KEY_SPACE:
            playing, play_pos = not playing, 0
        elif key in (KEY_ABSENT, KEY_HIDDEN):
            labels.set(frame_id, "absent" if key == KEY_ABSENT else "hidden")
            playing = False
            idx += 1
        elif key in KEY_ENTER:
            playing = False
            point = point_on_enter(labels.get(frame_id), hints.get(frame_id))
            if point is not None:
                labels.set(frame_id, "visible", point)
            idx += 1
        elif key in KEY_BACKSPACE:
            playing = False
            idx = max(0, idx - 1)
    cv2.destroyAllWindows()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--venue", type=Path, required=True, help="оттуда берётся target_fps пайплайна")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", type=int, default=200, help="сколько кадров, равномерно по видео")
    parser.add_argument("--scale", type=float, default=1.0, help="масштаб окна")
    parser.add_argument("--frames", type=Path, default=None,
                        help="файл с номерами кадров (по одному в строке) вместо равномерной выборки")
    parser.add_argument("--hints", type=Path, default=None, help="догадки модели: parquet с frame_id, x, y")
    args = parser.parse_args(argv)

    venue = load_venue(args.venue)
    clip = Clip(args.video)
    if args.frames:
        frame_ids = [int(line) for line in args.frames.read_text().split()]
    else:
        frame_ids = spread(sampled_frame_ids(clip.total, clip.fps, venue.target_fps), args.count)
    labels = BallLabels(args.out, src_fps=clip.fps)
    print(__doc__.split("\n\n", 2)[2])
    run(clip, labels, frame_ids, args.scale, load_hints(args.hints) if args.hints else None)
    c = labels.counts()
    done = sum(labels.get(i) is not None for i in frame_ids)
    print(f"размечено {done}/{len(frame_ids)}: мяч виден {c['visible']}, нет в кадре {c['absent']}, "
          f"не видно {c['hidden']} -> {args.out}")


if __name__ == "__main__":
    main()
