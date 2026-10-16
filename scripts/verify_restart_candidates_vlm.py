"""Платная проверка CV-кандидатов стандартных положений моделью Qwen (локальные данные, вне Git).

По умолчанию — сухой прогон: кандидаты, кадры и оценка токенов без обращений к API.
С --apply каждый ответ кэшируется в output/real-qwen/restart-vlm; повторный запуск не платит дважды.

python scripts/verify_restart_candidates_vlm.py [--apply]
"""
import argparse
import json
from hashlib import sha256
from pathlib import Path

import cv2
import polars as pl

from aifootball.perception.frames import iter_frames
from aifootball.processor.candidates import restart_candidates
from aifootball.processor.qwen import QwenClient, QwenConfig, QwenError
from aifootball.understanding.types import FrameAsset, Window

FRAGMENTS = [
    ('yaroslavl-60-240', 'data/raw/yaroslavl_futsal_n4WAFg0FfV4_60-240.webm',
     'output/analysis-acceptance/processor-cd7da23d0e7e4ab78c4bc2e9c195e193', 'data/gt/yaroslavl-60-240/touches.parquet'),
    ('yaroslavl-600-780', 'data/raw/yaroslavl_futsal_n4WAFg0FfV4_600-780.mp4',
     'data/matches/yaroslavl-600-780-v2', 'data/gt/yaroslavl-600-780/touches.parquet'),
]
OUT = Path('output/real-qwen/restart-vlm')
LOOSE = {'max_speed': 1.5, 'min_duration_s': 1.0}
BEFORE_S, AFTER_S, FPS = 1.5, 3.0, 2
MAX_REQUESTS, MAX_INPUT, MAX_OUTPUT = 22, 400_000, 20_000
TOKENS_PER_FRAME = 1600
RESTARTS = ('kick_in', 'corner', 'goal_clearance', 'free_kick', 'kickoff')

PROMPT = """Ты анализируешь короткий фрагмент любительского матча по футзалу. Камера неподвижна, сверху и сбоку.
На кадрах красным кругом отмечен игрок, который по данным трекинга стоит у линии поля. Рядом с каждым кадром указано window_ms.
Определи, что происходит с мячом: возобновляется ли игра стандартным положением с участием отмеченного игрока.
Варианты restart: kick_in (ввод из-за боковой линии), corner (угловой), goal_clearance (ввод мяча вратарём),
free_kick (штрафной), kickoff (начальный удар с центра), none (мяч в игре, игрок просто стоит у линии), unclear (не видно).
Не угадывай: если мяча не видно или кадры не позволяют решить, ставь unclear.
Верни только JSON: {"restart": "...", "ball_out_of_play": true|false|null, "marked_player_takes_restart": true|false|null,
"team_color": "цвет формы команды, вводящей мяч, или null", "confidence": число от 0 до 1, "reason": "одно короткое предложение по-русски"}"""


def frames_for(candidate, video, tracks, out):
    start_ms = max(0, round((candidate['start_s'] - BEFORE_S) * 1000)); end_ms = round((candidate['start_s'] + AFTER_S) * 1000)
    rows = tracks.filter(pl.col('track_id') == candidate['track_id'])
    assets = []
    for frame_id, ts, frame in iter_frames(Path(video), FPS, start_ms=start_ms, end_ms=end_ms):
        near = rows.with_columns(d=(pl.col('ts') - ts).abs()).filter(pl.col('d') <= 0.3).sort('d')
        if near.height:
            r = near.row(0, named=True); cx, cy = int((r['x1'] + r['x2']) / 2), int((r['y1'] + r['y2']) / 2)
            radius = int(max(r['x2'] - r['x1'], r['y2'] - r['y1']) * 0.9) + 20
            cv2.circle(frame, (cx, cy), radius, (0, 0, 255), 6)
        scale = 1280 / max(frame.shape[:2])
        image = cv2.resize(frame, (round(frame.shape[1] * scale), round(frame.shape[0] * scale)), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 82]); raw = encoded.tobytes()
        digest = sha256(raw).hexdigest(); path = out / f'{digest[:24]}.jpg'; path.write_bytes(raw)
        assets.append(FrameAsset(digest[:24], frame_id, round(ts * 1000), path, digest, None))
    return Window(f"restart-{candidate['start_s']:.2f}", start_ms, end_ms + 1, tuple(assets), None, (candidate['track_id'],), 'frames')


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--apply', action='store_true'); args = parser.parse_args()
    client = QwenClient(QwenConfig.from_env()) if args.apply else None
    OUT.mkdir(parents=True, exist_ok=True)
    spent = {'requests': 0, 'input': 0, 'output': 0}; rows = []
    for fragment, video, folder, gt in FRAGMENTS:
        state = pl.read_parquet(Path(folder) / 'state.parquet'); tracks = pl.read_parquet(Path(folder) / 'tracks.parquet')
        pitch = json.loads((Path(folder) / 'metrics.json').read_text())['pitch']
        dead = pl.read_parquet(gt).filter(pl.col('event') == 'dead')['ts'].to_list()
        for c in restart_candidates(state, pitch['length_m'], pitch['width_m'], **LOOSE):
            key = f"{fragment}-{round(c['start_s'] * 1000)}"; cache = OUT / f'{key}.json'
            truth = any(d - 1 <= c['start_s'] <= d + 7 for d in dead)
            if cache.exists():
                answer = json.loads(cache.read_text())
            else:
                folder = OUT / key; folder.mkdir(exist_ok=True)
                window = frames_for(c, video, tracks, folder)
                estimate = len(window.frames) * TOKENS_PER_FRAME + 800
                if not args.apply:
                    rows.append({'key': key, 'truth': truth, 'frames': len(window.frames), 'estimate': estimate}); continue
                if spent['requests'] >= MAX_REQUESTS or spent['input'] + estimate > MAX_INPUT or spent['output'] >= MAX_OUTPUT:
                    print('Лимит прогона исчерпан, остановка'); break
                try:
                    result = client.infer(window, PROMPT, max_output_tokens=400)
                except QwenError as exc:
                    spent['requests'] += 1; print(key, 'ошибка', exc.code); continue
                usage = result.usage or {}
                answer = {'candidate': c, 'document': result.document, 'usage': usage, 'request_id': result.request_id,
                          'model': result.response_model, 'frames': len(window.frames)}
                cache.write_text(json.dumps(answer, ensure_ascii=False, indent=1))
                spent['requests'] += 1; spent['input'] += usage.get('prompt_tokens', 0); spent['output'] += usage.get('completion_tokens', 0)
            doc = answer['document']
            positive = doc.get('restart') in RESTARTS
            rows.append({'key': key, 'truth': truth, 'restart': doc.get('restart'), 'positive': positive,
                         'confidence': doc.get('confidence'), 'reason': doc.get('reason'), 'team_cv': c['team'],
                         'team_color': doc.get('team_color'), 'usage': answer.get('usage')})
    if not args.apply:
        print(json.dumps({'candidates': len(rows), 'estimated_input_tokens': sum(r.get('estimate', 0) for r in rows)}, ensure_ascii=False)); return
    for r in rows: print(f"{r['key']:28} эталон={'да ' if r['truth'] else 'нет'} Qwen={r['restart']:15} conf={r['confidence']} · {r['reason']}")
    tp = sum(r['truth'] and r['positive'] for r in rows); fp = sum(not r['truth'] and r['positive'] for r in rows)
    fn = sum(r['truth'] and not r['positive'] for r in rows); tn = sum(not r['truth'] and not r['positive'] for r in rows)
    usage = [r['usage'] or {} for r in rows]
    summary = {'candidates': len(rows), 'cv_precision': f"{tp + fn}/{len(rows)}", 'after_qwen_precision': f'{tp}/{tp + fp}',
               'qwen_kept_true': f'{tp}/{tp + fn}', 'qwen_rejected_false': f'{tn}/{tn + fp}',
               'input_tokens': sum(u.get('prompt_tokens', 0) for u in usage), 'output_tokens': sum(u.get('completion_tokens', 0) for u in usage)}
    (OUT / 'summary.json').write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
