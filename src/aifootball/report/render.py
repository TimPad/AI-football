"""Сборка report.html из цифр отчёта (analytics.report_data) — один файл, всё внутри."""

from html import escape

from aifootball.report.svg import heatmap_svg, line_chart_svg, thirds_svg

TABS = (("stats", "Статистика"), ("players", "Игроки"), ("moments", "Моменты"))

CSS = """
:root{--bg:#f2f3f5;--card:#fff;--ink:#111;--muted:#7a8390;--head:#1c2430}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,Segoe UI,Roboto,sans-serif;font-size:14px}
.wrap{max-width:480px;margin:0 auto}
header{background:var(--head);color:#fff;padding:16px 16px 0}
header .teams{display:flex;justify-content:space-between;align-items:center;gap:8px}
header .dot{width:36px;height:36px;border-radius:50%;flex:none}
header .title{text-align:center;font-weight:700;font-size:16px}
header .sub{color:#9aa4b2;font-size:12px;text-align:center;margin-top:4px}
nav.tabs{display:flex;justify-content:space-around;margin-top:12px}
nav.tabs button{background:none;border:0;color:#9aa4b2;font-weight:600;font-size:14px;padding:10px 4px;cursor:pointer}
nav.tabs button.on{color:#fff;border-bottom:3px solid #fff}
.seg{display:flex;background:#e3e6ea;border-radius:20px;margin:12px 16px;padding:3px}
.seg button{flex:1;border:0;background:none;padding:7px;border-radius:16px;font-weight:600;cursor:pointer;color:var(--ink)}
.seg button.on{background:var(--head);color:#fff}
section{display:none}section.on{display:block}
.card{background:var(--card);border-radius:14px;margin:12px 16px;padding:14px}
.card h3{text-align:center;margin:0 0 12px;font-size:16px}
.row{margin:12px 0}.row .t{display:flex;justify-content:space-between;gap:8px}.row .t b{text-align:center}
.bars{display:flex;gap:12px;margin-top:5px}.bar{flex:1;height:6px;background:#eceef1;border-radius:3px;position:relative}
.bar i{position:absolute;top:0;bottom:0;border-radius:3px}.bar.l i{right:0}.bar.r i{left:0}
.note{font-size:12px;color:var(--muted);text-align:center;margin-top:8px}
.warn{font-size:12px;color:#b45309;text-align:center}
svg.pitch{width:100%;height:auto;display:block;border-radius:6px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:6px 3px;text-align:right}
td:first-child,th:first-child{text-align:left}tr+tr td{border-top:1px solid #eee}
details summary{list-style:none;cursor:pointer}details summary::-webkit-details-marker{display:none}
details[open]{background:#fafbfc}.ava{width:30px;height:40px;object-fit:cover;border-radius:4px;vertical-align:middle;margin-right:6px}
.moment img{width:100%;border-radius:8px;display:block;margin-bottom:8px}
.moment .v{font-size:20px;font-weight:700}
.players-table,.player-summary{table-layout:fixed}
.players-table th:nth-child(1),.player-summary td:nth-child(1){width:40%}
.players-table th:nth-child(2),.player-summary td:nth-child(2){width:18%}
.players-table th:nth-child(3),.player-summary td:nth-child(3){width:14%}
.players-table th:nth-child(4),.player-summary td:nth-child(4){width:16%}
.players-table th:nth-child(5),.player-summary td:nth-child(5){width:12%}
td.player-detail{padding:0}
.team-view{display:none}.team-view.on{display:block}
"""

JS = """
let period='all',tab='stats';
function show(){document.querySelectorAll('section').forEach(s=>s.classList.toggle('on',
 s.dataset.period===period&&s.dataset.tab===tab));
 document.querySelectorAll('[data-set-period]').forEach(b=>b.classList.toggle('on',b.dataset.setPeriod===period));
 document.querySelectorAll('[data-set-tab]').forEach(b=>b.classList.toggle('on',b.dataset.setTab===tab));}
document.querySelectorAll('[data-set-period]').forEach(b=>b.onclick=()=>{period=b.dataset.setPeriod;show()});
document.querySelectorAll('[data-set-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.setTab;show()});
document.querySelectorAll('.team-switch button').forEach(b=>b.onclick=()=>{const box=b.closest('.card');
 box.querySelectorAll('.team-switch button').forEach(x=>x.classList.toggle('on',x===b));
 box.querySelectorAll('.team-view').forEach(v=>v.classList.toggle('on',v.dataset.team===b.dataset.team));});
show();
"""


def image_requests(data: dict) -> dict[str, dict]:
    """Какие кадры вырезать из видео: миниатюры игроков и стоп-кадры моментов всех периодов."""
    req = {f"thumb:{tid}": r for tid, r in data["thumbs"].items()}
    for p in data["periods"]:
        for i, m in enumerate(p["moments"]):
            if m["still"] is not None:
                req[f"moment:{p['key']}:{i}"] = m["still"]
    return req


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _row(name: str, a: float, b: float, fmt: str, colors: dict) -> str:
    peak = max(a, b) or 1
    return (f'<div class="row"><div class="t"><span>{fmt.format(a)}</span><b>{name}</b><span>{fmt.format(b)}</span></div>'
            f'<div class="bars"><div class="bar l"><i style="width:{a / peak * 100:.0f}%;background:{colors["A"]}"></i></div>'
            f'<div class="bar r"><i style="width:{b / peak * 100:.0f}%;background:{colors["B"]}"></i></div></div></div>')


def _team_switch(names: dict) -> str:
    return ('<div class="seg team-switch" style="margin:0 0 10px">'
            + "".join(f'<button data-team="{t}" class="{"on" if t == "A" else ""}">{escape(names[t])}</button>'
                      for t in ("A", "B")) + "</div>")


def _stats(p: dict, data: dict) -> str:
    names, colors, pitch = data["match"]["teams"], data["match"]["colors"], data["pitch"]
    a, b = p["teams"]["A"], p["teams"]["B"]
    warn = '<div class="warn">Мало данных: команда большую часть времени вне кадра</div>' if a["low_data"] or b["low_data"] else ""
    if p.get("input_quality", {}).get("suspect_steps", 0):
        warn += ('<div class="warn">В траекториях есть резкие скачки. '
                 'Дистанцию и скорость следует сверить по видео.</div>')
    overview = "".join([
        _row("Дистанция", a["distance_m"] / 1000, b["distance_m"] / 1000, "{:.2f} км", colors),
        _row("м/мин наблюдения", a["m_per_min"], b["m_per_min"], "{:.0f}", colors),
        _row("Бег быстрее 4 м/с", a["hsr_m"], b["hsr_m"], "{:.0f} м", colors),
        _row("Спринты", a["sprints"], b["sprints"], "{:.0f}", colors),
        _row("Компактность", a["compactness_m2"], b["compactness_m2"], "{:.0f} м²", colors),
        _row("Ширина", a["width_m"], b["width_m"], "{:.1f} м", colors),
        _row("Глубина", a["depth_m"], b["depth_m"], "{:.1f} м", colors),
    ])
    views = []
    for t in ("A", "B"):
        thirds = p["thirds"][t]
        thirds_html = (thirds_svg(thirds, pitch["length_m"], pitch["width_m"], colors[t])
                       + '<div class="note">Доля времени в своей / средней / чужой трети. Свои ворота слева</div>'
                       if thirds else '<div class="note">Направление атаки не определено — трети не показаны</div>')
        views.append(f'<div class="team-view {"on" if t == "A" else ""}" data-team="{t}">{thirds_html}'
                     f'<div style="height:10px"></div>'
                     f'{heatmap_svg(p["teams"][t]["heatmap_s"], pitch["length_m"], pitch["width_m"], colors[t], pitch["cell_m"])}'
                     f'<div class="note">Где проводили время полевые игроки</div></div>')
    s = p["series"]
    chart = line_chart_svg(s["start_min"], {"A": s["A"], "B": s["B"]}, colors)
    ball = ""
    if "ball" in p:
        poss, passes = p["ball"]["possession"], p["ball"]["passes"]
        ball = (f'<div class="card"><h3>Владение и передачи (приблизительно)</h3>'
                + _row("Владение", poss["possession_pct"]["A"], poss["possession_pct"]["B"], "{:.0f}%", colors)
                + _row("Передачи", passes["passes_total"]["A"], passes["passes_total"]["B"], "{:.0f}", colors)
                + _row("Точность передач", passes["pass_accuracy_pct"]["A"], passes["pass_accuracy_pct"]["B"], "{:.0f}%", colors)
                + f'<div class="warn">{escape(p["ball"]["caveat"])}</div></div>')
    return (f'<div class="card"><h3>Обзор матча</h3>{warn}{overview}</div>'
            f'<div class="card"><h3>Где играла команда</h3>{_team_switch(names)}{"".join(views)}</div>'
            f'<div class="card"><h3>По ходу матча</h3>{chart}'
            f'<div class="note">Метров в минуту наблюдения на полевого игрока, по 5 минут</div></div>{ball}')


def _players(p: dict, data: dict, images: dict) -> str:
    names, colors, pitch = data["match"]["teams"], data["match"]["colors"], data["pitch"]
    views = []
    for t in ("A", "B"):
        rows = []
        for r in (r for r in p["players"] if r["team"] == t):
            img = images.get(f"thumb:{r['track_id']}")
            ava = f'<img class="ava" src="{img}" alt="">' if img else ""
            vmax = f"{r['vmax_ms']:.1f} м/с" if r["vmax_ms"] is not None else "—"
            card = (f'{heatmap_svg(r["heatmap_s"], pitch["length_m"], pitch["width_m"], colors[t], pitch["cell_m"])}'
                    f'<table><tr><td>Время в кадре</td><td>{_clock(r["observed_s"])}</td></tr>'
                    f'<tr><td>Дистанция</td><td>{r["distance_m"]:.0f} м</td></tr>'
                    f'<tr><td>м/мин наблюдения</td><td>{r["m_per_min"]:.0f}</td></tr>'
                    f'<tr><td>Спринты</td><td>{r["sprints"]}</td></tr>'
                    f'<tr><td>Бег быстрее 4 м/с</td><td>{r["hsr_m"]:.0f} м</td></tr>'
                    f'<tr><td>Макс. скорость (устойчивая)</td><td>{vmax}</td></tr></table>')
            rows.append(f'<tr><td colspan="5" class="player-detail"><details><summary><table class="player-summary"><tr>'
                        f'<td>{ava}{escape(r["label"])}</td><td>{_clock(r["observed_s"])}</td>'
                        f'<td>{r["distance_m"] / 1000:.2f}</td><td>{r["m_per_min"]:.0f}</td><td>{r["sprints"]}</td>'
                        f'</tr></table></summary>{card}</details></td></tr>')
        body = "".join(rows) or '<tr><td colspan="5">Нет треков дольше минуты</td></tr>'
        views.append(f'<div class="team-view {"on" if t == "A" else ""}" data-team="{t}"><table class="players-table">'
                     f'<tr><th>Игрок</th><th>Время</th><th>км</th><th>м/мин</th><th>Спр.</th></tr>{body}</table></div>')
    return (f'<div class="card">{_team_switch(names)}{"".join(views)}'
            '<div class="note">Строки — треки, а не люди: при заменах и столкновениях один человек может '
            'дать несколько строк. Узнать себя можно по миниатюре.</div></div>')


def _moments(p: dict, data: dict, images: dict) -> str:
    names = data["match"]["teams"]
    cards = []
    for i, m in enumerate(p["moments"]):
        img = images.get(f"moment:{p['key']}:{i}")
        who = f'{escape(names[m["team"]])}' + (f' · {escape(m["label"])}' if m["label"] else "")
        pic = f'<img src="{img}" alt="">' if img else ""
        cards.append(f'<div class="card moment">{pic}'
                     f'<div>{escape(m["title"])}</div><div class="v">{escape(m["value"])}</div>'
                     f'<div class="note" style="text-align:left">{_clock(m["ts"])} · {who}</div></div>')
    return "".join(cards) or '<div class="card"><div class="note">Моментов нет</div></div>'


def render_html(data: dict, images: dict[str, str]) -> str:
    match, colors = data["match"], data["match"]["colors"]
    names = match["teams"]
    halves = "" if match["halves_found"] else " · таймы не определены"
    if match.get("video_duration_estimated"):
        halves += " · длительность записи оценена"
    header = (f'<header><div class="teams"><div class="dot" style="background:{colors["A"]}"></div>'
              f'<div><div class="title">{escape(names["A"])} — {escape(names["B"])}</div>'
              f'<div class="sub">обработано {_clock(match["processed_s"])} из {_clock(match["video_s"])}{halves}</div></div>'
              f'<div class="dot" style="background:{colors["B"]}"></div></div>'
              '<nav class="tabs">' + "".join(f'<button data-set-tab="{k}">{n}</button>' for k, n in TABS) + '</nav></header>')
    seg = ('<div class="seg">' + "".join(f'<button data-set-period="{p["key"]}">{escape(p["name"])}</button>'
                                          for p in data["periods"]) + "</div>")
    sections = []
    for p in data["periods"]:
        sections.append(f'<section data-period="{p["key"]}" data-tab="stats">{_stats(p, data)}</section>')
        sections.append(f'<section data-period="{p["key"]}" data-tab="players">{_players(p, data, images)}</section>')
        sections.append(f'<section data-period="{p["key"]}" data-tab="moments">{_moments(p, data, images)}</section>')
    title = escape(f'{names["A"]} — {names["B"]}')
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>'
            f'<style>{CSS}</style></head><body><div class="wrap">{header}{seg}{"".join(sections)}</div>'
            f'<script>{JS}</script></body></html>')
