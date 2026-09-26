"""Разметка углов футзального поля и его центра по кадру-фону (без игроков).

    python -m aifootball.tools.mark_field --video V --venue DIR [--scale 0.5]

Инструмент по очереди называет точку (в терминале), вы кликаете её на кадре.
Мышь: левый клик — поставить точку. Клавиши (не зависят от раскладки):
    1          точку не видно (закрыта, за кадром) — пропустить
    Backspace  вернуться к предыдущей точке
    Enter      сохранить (когда все точки пройдены)
    Esc        выйти без сохранения
Результат — <venue>/field_points.json: сырые пиксели кадра по именам точек.
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from aifootball.tools.ball_labels import render_view

POINTS = [
    ("far_bench", "угол у ДАЛЬНИХ ворот, со стороны СКАМЕЕК"),
    ("far_stands", "угол у ДАЛЬНИХ ворот, со стороны ТРИБУН"),
    ("near_stands", "угол у БЛИЖНИХ ворот, со стороны ТРИБУН"),
    ("near_bench", "угол у БЛИЖНИХ ворот, со стороны СКАМЕЕК"),
    ("center", "ЦЕНТР поля (центральная точка)"),
]
KEY_ESC, KEY_SKIP, KEY_SPACE = 27, ord("1"), 32
KEY_ENTER = {10, 13}
KEY_BACKSPACE = {8, 127}
WINDOW = "mark_field"


def background(video: Path, samples: int = 40) -> np.ndarray:
    """Медиана кадров по всему видео: игроки движутся и исчезают, разметка остаётся."""
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    for frame_id in np.linspace(0, total - 1, samples).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_id))
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    if not frames:
        sys.exit(f"не читаются кадры: {video}")
    return np.median(np.stack(frames), axis=0).astype(np.uint8)


def save_points(path: Path, points: dict[str, tuple[float, float] | None]) -> None:
    data = {name: None if p is None else [round(p[0], 1), round(p[1], 1)] for name, p in points.items()}
    path.write_text(json.dumps({"points_px": data}, ensure_ascii=False, indent=2), encoding="utf-8")


def load_points(path: Path) -> dict[str, tuple[float, float] | None]:
    data = json.loads(path.read_text(encoding="utf-8"))["points_px"]
    return {name: None if p is None else (float(p[0]), float(p[1])) for name, p in data.items()}


def collect(frame: np.ndarray, scale: float) -> dict | None:
    placed: dict[str, tuple[float, float] | None] = {}
    ui = {"cursor": None, "click": None}

    def on_mouse(event, x, y, flags, param):
        ui["cursor"] = (int(x / scale), int(y / scale))
        if event == cv2.EVENT_LBUTTONDOWN:
            ui["click"] = (x / scale, y / scale)

    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW, on_mouse)
    idx, announced = 0, -1
    while True:
        if idx != announced:
            print(f"\n{idx + 1}/{len(POINTS)}: {POINTS[idx][1]}" if idx < len(POINTS)
                  else "\nвсе точки пройдены: Enter — сохранить, Backspace — поправить последнюю")
            announced = idx
        header = f"{min(idx + 1, len(POINTS))}/{len(POINTS)} {POINTS[idx][0] if idx < len(POINTS) else 'done: Enter'}"
        shown = render_view(frame, scale, None, ui["cursor"], header)
        for i, (name, _) in enumerate(POINTS):
            p = placed.get(name)
            if p is not None:
                c = (int(p[0] * scale), int(p[1] * scale))
                cv2.circle(shown, c, 7, (0, 0, 255), 2)
                cv2.putText(shown, str(i + 1), (c[0] + 8, c[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        cv2.imshow(WINDOW, shown)
        key = cv2.waitKey(30) & 0xFF
        if ui["click"] is not None:
            point, ui["click"] = ui["click"], None
            if idx < len(POINTS):
                placed[POINTS[idx][0]] = point
                print(f"   поставлена ({point[0]:.0f}, {point[1]:.0f})")
                idx += 1
        elif key == KEY_ESC:
            cv2.destroyAllWindows()
            return None
        elif key == KEY_SKIP and idx < len(POINTS):
            placed[POINTS[idx][0]] = None
            print("   пропущена: не видно")
            idx += 1
        elif key in KEY_BACKSPACE and idx > 0:
            idx -= 1
            placed.pop(POINTS[idx][0], None)
        elif key in KEY_ENTER and idx >= len(POINTS):
            cv2.destroyAllWindows()
            return placed


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--venue", type=Path, required=True)
    parser.add_argument("--scale", type=float, default=1.0, help="масштаб окна")
    args = parser.parse_args(argv)

    print("строю фон без игроков (медиана 40 кадров)...")
    frame = background(args.video)
    print(__doc__.split("\n\n", 2)[2])
    points = collect(frame, args.scale)
    if points is None:
        print("выход без сохранения")
        return
    path = args.venue / "field_points.json"
    save_points(path, points)
    print(f"сохранено -> {path}")


if __name__ == "__main__":
    main()
