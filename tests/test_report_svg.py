import xml.etree.ElementTree as ET

from aifootball.report.svg import heatmap_svg, line_chart_svg, thirds_svg


def _parse(svg):
    return ET.fromstring(svg)  # падает, если SVG не XML


def test_heatmap_svg_is_xml_with_cells():
    grid = [[0.0] * 20 for _ in range(40)]
    grid[5][5] = 10.0
    root = _parse(heatmap_svg(grid, 40.0, 20.0, "#1fae4b"))
    rects = [e for e in root.iter() if e.tag.endswith("rect") and e.get("class") == "cell"]
    assert len(rects) == 1


def test_thirds_svg_has_labels():
    svg = thirds_svg([30, 44, 26], 40.0, 20.0, "#f07a1a")
    _parse(svg)
    assert "30%" in svg and "44%" in svg and "26%" in svg


def test_line_chart_skips_missing_points():
    svg = line_chart_svg([0.0, 5.0, 10.0], {"A": [100.0, None, 90.0], "B": [95.0, 97.0, 99.0]},
                         {"A": "#1fae4b", "B": "#f07a1a"})
    root = _parse(svg)
    lines = [e for e in root.iter() if e.tag.endswith("polyline")]
    assert len(lines) == 3  # у A пропуск рвёт линию на две



def test_short_period_chart_draws_visible_points():
    root = _parse(line_chart_svg([0.], {'A':[100.], 'B':[90.]}, {'A':'#1fae4b','B':'#f07a1a'}))
    circles = [e for e in root.iter() if e.tag.endswith('circle')]
    assert len(circles) == 2 and all(float(e.get('r')) > 0 for e in circles)
