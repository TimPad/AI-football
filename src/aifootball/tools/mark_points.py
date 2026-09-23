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

from aifootball.tools.marking import (
    finish_problem,
    parse_meters,
    save_homography,
    save_polygon,
    topdown_preview,
)
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
                xm, ym = parse_meters(answer)
            except ValueError as error:
                print(f"  {error}. Точка не добавлена — кликните её ещё раз")
                return
            print(f"  точка {len(pixels) + 1}: x = {xm} м, y = {ym} м")
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
            problem = finish_problem(pixels, homography=ask_meters)
            if problem:
                print(problem)
                continue
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
    loo = info["leave_one_out_error_m"]
    print(f"ошибка без каждой точки (честная): {loo} м" if loo is not None
          else "честная ошибка не считается: нужно 5 точек или больше")
    preview = topdown_preview(frame, load_venue(args.venue).H, venue.length_m, venue.width_m, venue.calib)
    cv2.imshow("topdown preview — любая клавиша", preview)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
