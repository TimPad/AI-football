"""Замер сборки фрагментов в людей по внешности (docs/superpowers/specs/2026-11-23-people-identity-design.md).

Папка --out (например data/people/hse) игнорируется Git: в ней кадры участников. Шаги:
  crops    — кадры фрагментов из видео: out/crops/<трек>_<n>.jpg и out/crops.json
  features — признаки фрагментов: out/features-<kind>.npz (kind: color | dino)
  cluster  — люди при порогах: по командам число людей, доля «Неразобранных» и сомнительных
  pairs    — пары для разметки глазами: out/pairs-<set>.json и листы out/sheets/<set>-NNN.jpg (6 пар на лист;
             на листе только номер пары, вариант и способ отбора не видны)
  score    — по разметке out/labels-<set>.json ({"<номер>": "same" | "different" | "unclear"})
Пример: .venv/bin/python scripts/eval_people.py crops --out data/people/hse --artifacts <...> --video <...> --venue <...>
"""

import argparse
import json
import random
import zipfile
from pathlib import Path

import cv2
import numpy as np

from aifootball.analytics.people import assemble, conflicts, mean_feature, units_from_index

KINDS = ['color', 'dino', 'siglip']
SHEET_H = 180
PER_SHEET = 6


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return float((c - r) / d), float((c + r) / d)


def auc(same: list[float], different: list[float]) -> float:
    """Площадь под ROC: доля пар (один человек, разные), где у «один человек» похожесть выше; ничья — половина."""
    if not same or not different:
        return float('nan')
    s, d = np.array(same)[:, None], np.array(different)[None, :]
    return float(((s > d).sum() + 0.5 * (s == d).sum()) / (s.size * d.size))


def paired_bootstrap(truth: list[bool], x: list[float], y: list[float], n: int = 2000, seed: int = 0):
    """95% интервал разницы AUC двух вариантов на одних и тех же парах."""
    rng = np.random.default_rng(seed)
    t, x, y = np.array(truth), np.array(x), np.array(y)
    diffs = []
    for _ in range(n):
        i = rng.integers(0, len(t), len(t))
        a = auc(list(x[i][t[i]]), list(x[i][~t[i]])) - auc(list(y[i][t[i]]), list(y[i][~t[i]]))
        if np.isfinite(a):
            diffs.append(a)
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def stratified(sims: dict, n: int, bands: int = 10, seed: int = 0) -> list:
    """n пар, поровну из полос по квантилям похожести."""
    rng = random.Random(seed)
    keys = sorted(sims, key=lambda k: sims[k])
    edges = np.linspace(0, len(keys), bands + 1).astype(int)
    per = [n // bands + (1 if b < n % bands else 0) for b in range(bands)]
    out = []
    for b in range(bands):
        band = keys[edges[b] : edges[b + 1]]
        out += rng.sample(band, min(per[b], len(band)))
    return out


def same_rate(labelled: list[tuple[float, bool]], bands: int = 8):
    """Доля «один человек» по полосам похожести (квантили размеченных): функция похожесть -> доля."""
    xs = sorted(labelled)
    edges = np.linspace(0, len(xs), bands + 1).astype(int)
    steps = []
    for b in range(bands):
        part = xs[edges[b] : edges[b + 1]]
        if part:
            steps.append((part[-1][0], sum(y for _, y in part) / len(part)))

    def p(s: float) -> float:
        for upper, rate in steps:
            if s <= upper:
                return rate
        return steps[-1][1]

    return p


def load_index(path: Path) -> dict:
    if path.suffix == '.zip':
        return json.loads(zipfile.ZipFile(path).read('track-index.json'))
    return json.loads(path.read_text())


def read_crops(out: Path) -> dict[int, list[np.ndarray]]:
    index = json.loads((out / 'crops.json').read_text())
    return {int(t): [cv2.imread(str(out / 'crops' / n)) for n in names] for t, names in index.items()}


def load_features(out: Path, kind: str) -> dict[int, np.ndarray]:
    data = np.load(out / f'features-{kind}.npz')
    return dict(zip(data['track_ids'].tolist(), data['features']))


def summary(index: dict, people) -> dict:
    info = {t['track_id']: t for t in index['tracks']}

    def sec(t):
        return sum(b - a for a, b in info[t]['intervals'])

    out = {}
    for team in 'AB':
        persons = [p for p in people.persons if p.team == team]
        loose = [u['track_id'] for u in people.unsorted if info[u['track_id']]['team'] == team]
        inside, rest = sum(p.seconds for p in persons), sum(sec(t) for t in loose)
        out[team] = {
            'people': len(persons),
            'unsorted_share': round(rest / max(inside + rest, 1e-9), 3),
            'doubtful': sum(len(p.doubtful) for p in persons),
            'top_seconds': [round(p.seconds) for p in persons[:15]],
        }
    return out


def cmd_crops(a):
    from aifootball import schemas
    from aifootball.perception.person_crops import extract_crops, pick_frames
    from aifootball.venue import load_venue

    venue = load_venue(a.venue)
    tracks = schemas.read(a.artifacts / 'tracks.parquet', 'tracks')
    usable = None
    if venue.is_ptz:
        from aifootball.geometry.registration import frame_homographies

        usable = set(frame_homographies(schemas.read(a.artifacts / 'registration.parquet', 'registration')))
    picks = pick_frames(tracks, (venue.frame_width, venue.frame_height), usable, venue.overlay)
    crops = extract_crops(a.video, picks)
    folder = a.out / 'crops'
    folder.mkdir(parents=True, exist_ok=True)
    index = {}
    for tid, images in sorted(crops.items()):
        names = []
        for n, image in enumerate(images):
            name = f'{tid}_{n}.jpg'
            cv2.imwrite(str(folder / name), image)
            names.append(name)
        index[str(tid)] = names
    (a.out / 'crops.json').write_text(json.dumps(index))
    print('фрагментов с кадрами:', len(index), 'кадров:', sum(map(len, index.values())))


def cmd_features(a):
    from aifootball.perception.appearance import TimmEmbedder, color_feature

    crops = read_crops(a.out)
    embed = (lambda images: [color_feature(i) for i in images]) if a.kind == 'color' else TimmEmbedder(a.kind, a.cache)
    ids, rows = [], []
    for tid, images in sorted(crops.items()):
        f = mean_feature(embed(images))
        if f is not None:
            ids.append(tid)
            rows.append(f)
    np.savez(a.out / f'features-{a.kind}.npz', track_ids=np.array(ids), features=np.stack(rows))
    print(a.kind, 'признаков:', len(ids))


def cmd_cluster(a):
    index = load_index(a.index)
    units = units_from_index(index, load_features(a.out, a.kind))
    for tau in a.threshold:
        people = assemble(units, tau, a.margin)
        print(a.kind, tau, json.dumps(summary(index, people), ensure_ascii=False))


def unit_key(u) -> str:
    return '-'.join(map(str, u.track_ids))


def sheet(out: Path, name: str, pairs: list[dict], crops: dict[int, list[np.ndarray]]):
    """Лист: строка на пару — номер, 3 кадра одной стороны, промежуток, 3 кадра другой."""

    def side(tracks):
        images = [c for t in tracks for c in crops.get(t, [])[:1]][:3] or [np.zeros((SHEET_H, 60, 3), np.uint8)]
        return [cv2.resize(i, (max(1, int(i.shape[1] * SHEET_H / i.shape[0])), SHEET_H)) for i in images]

    rows = []
    for p in pairs:
        label = np.full((SHEET_H, 90, 3), 255, np.uint8)
        cv2.putText(label, f'#{p["id"]}', (5, SHEET_H // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        gap = np.full((SHEET_H, 40, 3), 255, np.uint8)
        rows.append(np.hstack([label, *side(p['a']), gap, *side(p['b'])]))
    width = max(r.shape[1] for r in rows)
    rows = [np.hstack([r, np.full((SHEET_H, width - r.shape[1], 3), 255, np.uint8)]) for r in rows]
    folder = out / 'sheets'
    folder.mkdir(exist_ok=True)
    cv2.imwrite(str(folder / name), np.vstack([np.vstack([r, np.full((8, width, 3), 200, np.uint8)]) for r in rows]))


def cmd_pairs(a):
    index = load_index(a.index)
    labelled = set()
    for f in a.out.glob('pairs-*.json'):
        labelled |= {(tuple(p['a']), tuple(p['b'])) for p in json.loads(f.read_text())}
    chosen = []
    if a.set == 'calib':
        for kind in a.kinds:
            units = units_from_index(index, load_features(a.out, kind))
            blocked = conflicts(units)
            sims = {
                (i, j): float(units[i].feature @ units[j].feature)
                for i in range(len(units))
                for j in range(i + 1, len(units))
                if not blocked[i, j] and units[i].feature is not None and units[j].feature is not None
            }
            for i, j in stratified(sims, a.n // len(a.kinds), seed=a.seed):
                chosen.append({'a': list(units[i].track_ids), 'b': list(units[j].track_ids), 'kind': kind})
    else:
        units = units_from_index(index, load_features(a.out, a.kind))
        people = assemble(units, a.tau, a.margin)
        by_track = {t: u for u in units for t in u.track_ids}
        rng = random.Random(a.seed)
        members = {
            p.key: list({unit_key(by_track[t]): by_track[t] for t in p.track_ids}.values()) for p in people.persons
        }
        multi = [k for k, us in members.items() if len(us) > 1]
        for _ in range(a.n_within * 20):
            if sum(1 for c in chosen if c['kind'] == 'within') >= a.n_within:
                break
            us = members[rng.choice(multi)]
            x, y = rng.sample(us, 2)
            chosen.append({'a': list(x.track_ids), 'b': list(y.track_ids), 'kind': 'within'})
        blocked = conflicts(units)
        pos = {unit_key(u): i for i, u in enumerate(units)}
        for _ in range(a.n_neighbor * 20):
            if sum(1 for c in chosen if c['kind'] == 'neighbor') >= a.n_neighbor:
                break
            key = rng.choice(list(members))
            x = rng.choice(members[key])
            options = [
                (np.mean([x.feature @ y.feature for y in us]), k)
                for k, us in members.items()
                if k != key and not any(blocked[pos[unit_key(x)], pos[unit_key(y)]] for y in us)
            ]
            if options:
                _, best = max(options)
                chosen.append(
                    {'a': list(x.track_ids), 'b': list(rng.choice(members[best]).track_ids), 'kind': 'neighbor'}
                )
    unique, seen = [], set(labelled)
    for c in chosen:
        k = (tuple(c['a']), tuple(c['b']))
        if k not in seen and k[::-1] not in seen:
            seen.add(k)
            unique.append(c)
    random.Random(a.seed).shuffle(unique)
    for n, c in enumerate(unique, 1):
        c['id'] = f'{a.set}{n}'
    (a.out / f'pairs-{a.set}.json').write_text(json.dumps(unique, ensure_ascii=False))
    crops = read_crops(a.out)
    for s in range(0, len(unique), PER_SHEET):
        sheet(a.out, f'{a.set}-{s // PER_SHEET + 1:03d}.jpg', unique[s : s + PER_SHEET], crops)
    print('пар:', len(unique), 'листов:', (len(unique) + PER_SHEET - 1) // PER_SHEET)


def cmd_score(a):
    index = load_index(a.index)
    pairs = json.loads((a.out / f'pairs-{a.set}.json').read_text())
    labels = json.loads((a.out / f'labels-{a.set}.json').read_text())
    known = [p for p in pairs if labels.get(p['id']) in ('same', 'different')]
    print(
        'размечено:', len(known), 'из', len(pairs), '· не понять:', sum(labels.get(p['id']) == 'unclear' for p in pairs)
    )
    if a.set == 'calib':
        sims = {}
        for kind in a.kinds:
            units = units_from_index(index, load_features(a.out, kind))
            by_track = {t: u for u in units for t in u.track_ids}
            sims[kind] = {
                p['id']: float(by_track[p['a'][0]].feature @ by_track[p['b'][0]].feature)
                for p in known
                if by_track[p['a'][0]].feature is not None and by_track[p['b'][0]].feature is not None
            }
        common = [p for p in known if all(p['id'] in sims[k] for k in a.kinds)]
        truth = [labels[p['id']] == 'same' for p in common]
        print('пар с признаками всех вариантов:', len(common), '· один человек:', sum(truth))
        for kind in a.kinds:
            v = [sims[kind][p['id']] for p in common]
            print(
                kind, 'AUC', round(auc([s for s, t in zip(v, truth) if t], [s for s, t in zip(v, truth) if not t]), 3)
            )
        for n, x in enumerate(a.kinds):
            for y in a.kinds[n + 1 :]:
                low, high = paired_bootstrap(
                    truth, [sims[x][p['id']] for p in common], [sims[y][p['id']] for p in common]
                )
                print(f'AUC {x} − {y}: 95% {low:+.3f}…{high:+.3f}')
        for kind in a.kinds:
            feats = load_features(a.out, kind)
            units = units_from_index(index, feats)
            by_track = {t: u for u in units for t in u.track_ids}

            def sim(p):
                x, y = by_track[p['a'][0]].feature, by_track[p['b'][0]].feature
                return None if x is None or y is None else float(x @ y)

            data = [(s, labels[p['id']] == 'same') for p in known if (s := sim(p)) is not None]
            rate = same_rate(data)
            for tau in a.threshold:
                people = assemble(units, tau, a.margin)
                within = []
                for person in people.persons:
                    us = list({unit_key(by_track[t]): by_track[t] for t in person.track_ids}.values())
                    within += [
                        (rate(float(x.feature @ y.feature)), x.seconds * y.seconds)
                        for n, x in enumerate(us)
                        for y in us[n + 1 :]
                    ]
                expected = sum(r * w for r, w in within) / max(sum(w for _, w in within), 1e-9)
                print(
                    kind,
                    tau,
                    'ожидаемая точность',
                    round(expected, 3),
                    json.dumps(summary(index, people), ensure_ascii=False),
                )
    else:
        for kind in ('within', 'neighbor'):
            part = [p for p in known if p['kind'] == kind]
            same = sum(labels[p['id']] == 'same' for p in part)
            low, high = wilson(same, len(part))
            print(kind, f'один человек {same}/{len(part)} = {same / max(len(part), 1):.3f} (95%: {low:.3f}–{high:.3f})')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='step', required=True)
    s = sub.add_parser('crops')
    s.add_argument('--artifacts', type=Path, required=True)
    s.add_argument('--video', type=Path, required=True)
    s.add_argument('--venue', type=Path, required=True)
    s = sub.add_parser('features')
    s.add_argument('--kind', choices=KINDS, required=True)
    s.add_argument('--cache', type=Path, default=Path('models/hf'))
    s = sub.add_parser('cluster')
    s.add_argument('--index', type=Path, required=True)
    s.add_argument('--kind', choices=KINDS, required=True)
    s.add_argument('--threshold', type=float, nargs='+', required=True)
    s.add_argument('--margin', type=float, default=0.05)
    s = sub.add_parser('pairs')
    s.add_argument('--index', type=Path, required=True)
    s.add_argument('--set', choices=['calib', 'final'], required=True)
    s.add_argument('--kinds', nargs='+', default=KINDS)
    s.add_argument('--n', type=int, default=210)
    s.add_argument('--kind', choices=KINDS)
    s.add_argument('--tau', type=float)
    s.add_argument('--margin', type=float, default=0.05)
    s.add_argument('--n-within', type=int, default=75)
    s.add_argument('--n-neighbor', type=int, default=75)
    s.add_argument('--seed', type=int, default=1)
    s = sub.add_parser('score')
    s.add_argument('--index', type=Path, required=True)
    s.add_argument('--set', choices=['calib', 'final'], required=True)
    s.add_argument('--kinds', nargs='+', default=KINDS)
    s.add_argument('--threshold', type=float, nargs='*', default=[])
    s.add_argument('--margin', type=float, default=0.05)
    for s in sub.choices.values():
        s.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    {'crops': cmd_crops, 'features': cmd_features, 'cluster': cmd_cluster, 'pairs': cmd_pairs, 'score': cmd_score}[
        a.step
    ](a)


if __name__ == '__main__':
    main()
