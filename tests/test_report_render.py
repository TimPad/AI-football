import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from report_fixtures import LENGTH, synthetic_match  # noqa: E402

from aifootball.analytics.report_data import build_report  # noqa: E402
from aifootball.report.render import image_requests, render_html  # noqa: E402


class _Venue:
    length_m, width_m, max_physical_speed = LENGTH, 20.0, 10.0


def _data():
    state, tracks = synthetic_match()
    return build_report(state, tracks, _Venue(), [(0.0, 100.0), (100.0, 200.0)],
                        {"A": "Зелёные <script>", "B": "Оранжевые"}, video_s=200.0)


def test_render_has_tabs_periods_and_escapes_names():
    html = render_html(_data(), images={})
    for key in ("all", "h1", "h2"):
        for tab in ("stats", "players", "moments"):
            assert f'data-period="{key}" data-tab="{tab}"' in html
    assert "Зелёные &lt;script&gt;" in html and "Зелёные <script>" not in html
    assert "<img" not in html  # без видео картинок нет


def test_image_requests_cover_thumbs_and_moments():
    data = _data()
    req = image_requests(data)
    assert "thumb:11" in req
    assert any(k.startswith("moment:all:") for k in req)


def test_render_inlines_images():
    data = _data()
    html = render_html(data, images={"thumb:11": "data:image/jpeg;base64,AAAA"})
    assert 'src="data:image/jpeg;base64,AAAA"' in html



def test_report_explains_estimated_duration():
    data = _data()
    data['match']['video_duration_estimated'] = True
    html = render_html(data, {})
    assert 'длительность записи оценена' in html


def test_ball_card_includes_pass_accuracy():
    data = _data()
    for p in data['periods']:
        p['ball'] = {'possession': {'possession_pct': {'A': 40., 'B': 60.}},
                     'passes': {'passes_total': {'A': 10, 'B': 20}, 'pass_accuracy_pct': {'A': 80., 'B': 90.}},
                     'caveat': 'Приблизительно'}
    html = render_html(data, {})
    assert 'Точность передач' in html and '80%' in html and '90%' in html


def test_input_quality_warning_visible_for_bad_trajectories():
    data = _data()
    data['periods'][0]['input_quality'] = {'suspect_steps':2}
    html = render_html(data, {})
    assert 'траекториях есть резкие скачки' in html
