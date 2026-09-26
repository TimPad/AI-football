"""Гомография и размер футзального поля по отмеченным точкам разметки (tools.mark_field).

    python -m aifootball.tools.fit_field --venue DIR [--write]

Размер поля неизвестен заранее: координаты точек заданы через длину L и ширину W, и подгонка
находит гомографию вместе с L и W. Масштаб дают точки с абсолютными размерами — центральный
круг (r = 3 м), стойки ворот (3 м), точки 6 и 10 м. Для каждой точки печатается ошибка:
неверно понятая или неточно поставленная точка видна сразу.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from aifootball.geometry.undistort import undistort_points
from aifootball.venue import Calibration, load_venue

# имя: (описание, x = ax*L + bx, y = ay*W + by). x — вдоль поля от дальних ворот, y — поперёк от скамеек.
FIELD_POINTS = {
    "far_bench": ("угол у ДАЛЬНИХ ворот, со стороны СКАМЕЕК", 0, 0, 0, 0),
    "far_stands": ("угол у ДАЛЬНИХ ворот, со стороны ТРИБУН", 0, 0, 1, 0),
    "near_stands": ("угол у БЛИЖНИХ ворот, со стороны ТРИБУН", 1, 0, 1, 0),
    "near_bench": ("угол у БЛИЖНИХ ворот, со стороны СКАМЕЕК", 1, 0, 0, 0),
    "half_bench": ("СРЕДНЯЯ линия у боковой со стороны СКАМЕЕК", 0.5, 0, 0, 0),
    "half_stands": ("СРЕДНЯЯ линия у боковой со стороны ТРИБУН", 0.5, 0, 1, 0),
    "center": ("ЦЕНТР поля (центральная точка)", 0.5, 0, 0.5, 0),
    "circle_bench": ("центральный КРУГ пересекает среднюю линию — со стороны СКАМЕЕК", 0.5, 0, 0.5, -3),
    "circle_stands": ("центральный КРУГ пересекает среднюю линию — со стороны ТРИБУН", 0.5, 0, 0.5, 3),
    "far_post_bench": ("ДАЛЬНИЕ ворота: основание стойки со стороны СКАМЕЕК", 0, 0, 0.5, -1.5),
    "far_post_stands": ("ДАЛЬНИЕ ворота: основание стойки со стороны ТРИБУН", 0, 0, 0.5, 1.5),
    "far_pen6": ("ДАЛЬНЯЯ точка пенальти (6 м от ворот)", 0, 6, 0.5, 0),
    "far_pen10": ("ДАЛЬНЯЯ точка 10 м от ворот", 0, 10, 0.5, 0),
    "near_post_bench": ("БЛИЖНИЕ ворота: основание стойки со стороны СКАМЕЕК", 1, 0, 0.5, -1.5),
    "near_post_stands": ("БЛИЖНИЕ ворота: основание стойки со стороны ТРИБУН", 1, 0, 0.5, 1.5),
    "near_pen6": ("БЛИЖНЯЯ точка пенальти (6 м от ворот)", 1, -6, 0.5, 0),
    "near_pen10": ("БЛИЖНЯЯ точка 10 м от ворот", 1, -10, 0.5, 0),
}


def field_xy(name: str, length: float, width: float) -> tuple[float, float]:
    _, ax, bx, ay, by = FIELD_POINTS[name]
    return ax * length + bx, ay * width + by


def fit_field(points_px: dict, calib: Calibration | None, length0: float = 40.0, width0: float = 20.0) -> dict:
    """points_px: имя -> сырые пиксели кадра (или None, если точку пропустили)."""
    names = [n for n, p in points_px.items() if p is not None and n in FIELD_POINTS]
    if len(names) < 4:
        raise ValueError(f"нужно минимум 4 точки, отмечено {len(names)}")
    px = undistort_points(np.array([points_px[n] for n in names], float), calib)
    coef = np.array([FIELD_POINTS[n][1:] for n in names], float)
    # без точек с абсолютным размером (круг, ворота, пенальти) масштаб не определить — размер фиксируем
    size_free = bool(np.any(coef[:, [1, 3]] != 0))

    def targets(length, width):
        return np.column_stack([coef[:, 0] * length + coef[:, 1], coef[:, 2] * width + coef[:, 3]])

    def project(h):
        H = np.append(h, 1.0).reshape(3, 3)
        q = np.column_stack([px, np.ones(len(px))]) @ H.T
        return q[:, :2] / q[:, 2:3]

    def residuals(t):
        length, width = (t[8], t[9]) if size_free else (length0, width0)
        return (project(t[:8]) - targets(length, width)).ravel()

    H0, _ = cv2.findHomography(px, targets(length0, width0), 0)
    t = np.concatenate([(H0 / H0[2, 2]).ravel()[:8], [length0, width0]])
    lam = 1e-3
    for _ in range(300):
        r = residuals(t)
        J = np.empty((len(r), len(t)))
        for j in range(len(t)):
            step = 1e-7 * max(1.0, abs(t[j]))
            t2 = t.copy()
            t2[j] += step
            J[:, j] = (residuals(t2) - r) / step
        A, g = J.T @ J, J.T @ r
        improved = False
        while lam < 1e12:
            delta = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-12), -g)
            if (residuals(t + delta) ** 2).sum() < (r ** 2).sum():
                t, lam, improved = t + delta, max(lam / 3, 1e-12), True
                break
            lam *= 5
        if not improved or np.abs(delta).max() < 1e-12:
            break
    length, width = (t[8], t[9]) if size_free else (length0, width0)
    err = np.linalg.norm(project(t[:8]) - targets(length, width), axis=1)
    return {
        "H": np.append(t[:8], 1.0).reshape(3, 3),
        "length_m": float(length),
        "width_m": float(width),
        "size_fitted": size_free,
        "errors_m": {n: float(e) for n, e in zip(names, err)},
        "rms_m": float(np.sqrt((err ** 2).mean())),
        "points": [{"name": n, "px": list(map(float, points_px[n])),
                    "m": list(map(float, field_xy(n, length, width)))} for n in names],
    }


def court_shapes(length: float, width: float) -> list[np.ndarray]:
    """Линии футзального поля в метрах: периметр, средняя, центральный круг, штрафные (дуги 6 м от стоек)."""
    def seg(a, b):
        return np.linspace(a, b, 80)

    def arc(c, r, t0, t1):
        t = np.linspace(t0, t1, 80)
        return np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)])

    L, W = length, width
    shapes = [seg((0, 0), (L, 0)), seg((L, 0), (L, W)), seg((L, W), (0, W)), seg((0, W), (0, 0)),
              seg((L / 2, 0), (L / 2, W)), arc((L / 2, W / 2), 3, 0, 2 * np.pi)]
    for x0, s in ((0.0, 1), (L, -1)):
        lo, hi = (x0, W / 2 - 1.5), (x0, W / 2 + 1.5)
        shapes += [arc(lo, 6, -np.pi / 2, 0) if s > 0 else arc(lo, 6, np.pi, 1.5 * np.pi),
                   arc(hi, 6, 0, np.pi / 2) if s > 0 else arc(hi, 6, np.pi / 2, np.pi),
                   seg((x0 + 6 * s, W / 2 - 1.5), (x0 + 6 * s, W / 2 + 1.5))]
    return shapes


def overlay_court(frame: np.ndarray, H: np.ndarray, calib: Calibration | None, length: float, width: float) -> np.ndarray:
    """Разметка поля по гомографии поверх исходного кадра (с дисторсией объектива) — проверка глазами."""
    H_inv = np.linalg.inv(H)
    out = frame.copy()
    for shape in court_shapes(length, width):
        q = np.column_stack([shape, np.ones(len(shape))]) @ H_inv.T
        px = q[:, :2] / q[:, 2:3]
        if calib is not None:
            n = (px - calib.K[:2, 2]) / calib.K[0, 0]
            px, _ = cv2.projectPoints(np.column_stack([n, np.ones(len(n))]), np.zeros(3), np.zeros(3), calib.K, calib.dist)
            px = px.reshape(-1, 2)
        cv2.polylines(out, [np.round(px).astype(np.int32).reshape(-1, 1, 2)], False, (255, 0, 255), 3, cv2.LINE_AA)
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--venue", type=Path, required=True)
    parser.add_argument("--write", action="store_true", help="записать homography.json")
    parser.add_argument("--exclude", nargs="*", default=[], help="не использовать эти точки")
    parser.add_argument("--overlay", type=Path, default=None, help="картинка: разметка поля поверх кадра")
    parser.add_argument("--video", type=Path, default=None, help="видео для --overlay (кадр-фон без игроков)")
    args = parser.parse_args(argv)

    from aifootball.tools.mark_field import background, load_points

    venue = load_venue(args.venue)
    points = load_points(args.venue / "field_points.json")
    for name in args.exclude:
        points[name] = None
    res = fit_field(points, venue.calib, venue.length_m, venue.width_m)
    size = "подобран" if res["size_fitted"] else "взят из venue.yaml (нет точек с абсолютным размером)"
    print(f"поле {res['length_m']:.2f} x {res['width_m']:.2f} м ({size}); средняя ошибка {res['rms_m']:.2f} м")
    for name, e in sorted(res["errors_m"].items(), key=lambda kv: -kv[1]):
        print(f"  {e:5.2f} м  {name:17s} {FIELD_POINTS[name][0]}")
    if args.overlay is not None:
        if args.video is None:
            parser.error("для --overlay нужен --video")
        cv2.imwrite(str(args.overlay), overlay_court(background(args.video), res["H"], venue.calib,
                                                      res["length_m"], res["width_m"]))
        print(f"наложение -> {args.overlay}")
    if args.write:
        data = {"H": res["H"].tolist(), "points": res["points"], "reprojection_error_m": round(res["rms_m"], 3),
                "leave_one_out_error_m": None, "length_m": round(res["length_m"], 2), "width_m": round(res["width_m"], 2)}
        (args.venue / "homography.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"записано -> {args.venue / 'homography.json'}; размер поля в venue.yaml обновите вручную")


if __name__ == "__main__":
    main()
