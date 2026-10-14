"""SVG для отчёта: поле с разметкой футзала, тепловая карта, трети, линейный график.

Координаты поля в SVG — метры (viewBox), свои ворота команды слева.
"""

from html import escape

LINE = "#ffffff"
GRASS = "#e9f3ea"
PAD = 0.6  # поля вокруг площадки, м


def _pitch_lines(length_m: float, width_m: float) -> str:
    """Разметка: контур, средняя линия, центральный круг 3 м, штрафные дуги 6 м, ворота 3 м."""
    cy = width_m / 2
    parts = [
        f'<rect x="0" y="0" width="{length_m}" height="{width_m}" fill="none" stroke="{LINE}" stroke-width="0.15"/>',
        f'<line x1="{length_m / 2}" y1="0" x2="{length_m / 2}" y2="{width_m}" stroke="{LINE}" stroke-width="0.15"/>',
        f'<circle cx="{length_m / 2}" cy="{cy}" r="3" fill="none" stroke="{LINE}" stroke-width="0.15"/>',
    ]
    for gx, sign in ((0.0, 1), (length_m, -1)):
        parts.append(f'<path d="M {gx} {cy - 6} A 6 6 0 0 {1 if sign > 0 else 0} {gx} {cy + 6}" '
                     f'fill="none" stroke="{LINE}" stroke-width="0.15"/>')
        parts.append(f'<line x1="{gx}" y1="{cy - 1.5}" x2="{gx}" y2="{cy + 1.5}" stroke="#555" stroke-width="0.5"/>')
    return "".join(parts)


def _svg(length_m: float, width_m: float, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="pitch" '
            f'viewBox="{-PAD} {-PAD} {length_m + 2 * PAD} {width_m + 2 * PAD}">'
            f'<rect x="{-PAD}" y="{-PAD}" width="{length_m + 2 * PAD}" height="{width_m + 2 * PAD}" fill="{GRASS}"/>'
            f'{body}{_pitch_lines(length_m, width_m)}</svg>')


def heatmap_svg(grid: list[list[float]], length_m: float, width_m: float, color: str, cell_m: float = 1.0) -> str:
    """Клетки с прозрачностью по доле от максимума; grid[ix][iy] — секунды в клетке."""
    peak = max((v for col in grid for v in col), default=0.0)
    cells = []
    if peak > 0:
        for ix, col in enumerate(grid):
            for iy, v in enumerate(col):
                if v > 0:
                    cells.append(f'<rect class="cell" x="{ix * cell_m}" y="{iy * cell_m}" width="{cell_m}" '
                                 f'height="{cell_m}" fill="{color}" fill-opacity="{0.15 + 0.85 * v / peak:.2f}"/>')
    return _svg(length_m, width_m, "".join(cells))


def thirds_svg(shares: list[int], length_m: float, width_m: float, color: str) -> str:
    """Три зоны (своя, средняя, чужая треть) с яркостью по доле времени и подписью «NN%»."""
    third = length_m / 3
    peak = max(shares) or 1
    body = []
    for k, share in enumerate(shares):
        x = k * third
        body.append(f'<rect x="{x}" y="0" width="{third}" height="{width_m}" fill="{color}" '
                    f'fill-opacity="{0.12 + 0.6 * share / peak:.2f}"/>')
        body.append(f'<rect x="{x + third / 2 - 3}" y="{width_m / 2 - 1.8}" width="6" height="3.6" rx="0.6" fill="#fff"/>')
        body.append(f'<text x="{x + third / 2}" y="{width_m / 2 + 1.0}" font-size="2.6" font-weight="700" '
                    f'text-anchor="middle" fill="#111">{share}%</text>')
    return _svg(length_m, width_m, "".join(body))


def line_chart_svg(x_values: list[float], series: dict[str, list[float | None]], colors: dict[str, str],
                   width: int = 320, height: int = 120) -> str:
    """Линии по командам; пропуск (None) рвёт линию. Подписи: минуты по x, значения по y."""
    values = [v for s in series.values() for v in s if v is not None]
    if not values or not x_values:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"></svg>'
    lo, hi = min(values) * 0.9, max(values) * 1.1 or 1.0
    x0, x1 = min(x_values), max(x_values) or 1.0
    left, right, top, bottom = 34, 8, 8, 18

    def px(x, y):
        fx = left + (x - x0) / ((x1 - x0) or 1) * (width - left - right)
        fy = top + (1 - (y - lo) / ((hi - lo) or 1)) * (height - top - bottom)
        return f"{fx:.1f},{fy:.1f}"

    parts = [f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#ddd"/>',
             f'<text x="2" y="{top + 8}" font-size="10" fill="#888">{hi:.0f}</text>',
             f'<text x="2" y="{height - bottom}" font-size="10" fill="#888">{lo:.0f}</text>']
    for x in x_values:
        parts.append(f'<text x="{px(x, lo).split(",")[0]}" y="{height - 4}" font-size="10" fill="#888" '
                     f'text-anchor="middle">{x:g}′</text>')
    for team, ys in series.items():
        run = []
        for x, y in list(zip(x_values, ys)) + [(None, None)]:
            if y is None:
                if run:
                    parts.append(f'<polyline fill="none" stroke="{escape(colors[team])}" stroke-width="2.5" '
                                 f'points="{" ".join(run)}"/>')
                run = []
            else:
                run.append(px(x, y))
                cx, cy = px(x, y).split(",")
                parts.append(f'<circle cx="{cx}" cy="{cy}" r="3" fill="{escape(colors[team])}">'
                             f'<title>{escape(team)}: {y:g} м/мин, {x:g} мин</title></circle>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">{"".join(parts)}</svg>'
