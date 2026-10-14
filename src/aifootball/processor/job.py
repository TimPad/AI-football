import base64
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED
import math
import yaml
from aifootball.analytics.exchange import (canonical, read_archive, load_json, ensure, uuid,
                                           hash_value, validate_result, ExchangeError, UNITS)


@dataclass(frozen=True)
class JobContext:
    contract: dict
    files: dict[str, bytes]


def read_job(path):
    files = read_archive(path, job=True)
    ensure({'job.json', 'venue.yaml', 'homography.json', 'pitch_polygon.json'} <= set(files), 'Неполный пакет задания')
    job = load_json(files['job.json'], 'job.json')
    try:
        ensure(job['contract_version'] == '1', 'Неподдерживаемая версия задания')
        for field in ['job_id', 'match_id']: uuid(job[field], field)
        context = job['context']; camera = context['camera']
        hash_value(job['context_hash'], 'context_hash')
        ensure(sha256(canonical(context)).hexdigest() == job['context_hash'], 'Изменён контекст задания')
        ensure(context['match_id'] == job['match_id'] and context['units'] == UNITS, 'Несогласованное задание')
        cfg = yaml.safe_load(files['venue.yaml']); proc = cfg['processing']
        ensure(cfg['pitch'] == context['pitch'] and cfg['venue_id'] == context['hall_id'] and
               proc['camera_profile_id'] == camera['id'] and proc['frame_width'] == camera['frame_width'] and
               proc['frame_height'] == camera['frame_height'] and
               load_json(files['homography.json'], 'homography.json')['H'] == camera['homography'] and
               load_json(files['pitch_polygon.json'], 'pitch_polygon.json')['points_px'] == camera['polygon_px'],
               'CV-геометрия не совпадает со снимком задания')
        calibration = load_json(files['calib.json'], 'calib.json') if 'calib.json' in files else None
        ensure(calibration == camera['calibration'], 'CV-геометрия объектива не совпадает')
        # Models are selected from the operator's trusted model directory, never arbitrary paths in a job.
        ensure(isinstance(proc['model'], str) and Path(proc['model']).name == proc['model'] and proc['model'].endswith('.pt'), 'Неверное имя модели')
        ensure(not proc.get('ball_model'), 'В этой версии задания используется только детектор игроков')
        return JobContext(job, files)
    except (KeyError, TypeError, yaml.YAMLError) as exc:
        raise ExchangeError('Неверная структура задания') from exc


def video_info(path):
    import cv2
    cap = cv2.VideoCapture(str(path))
    try:
        ensure(cap.isOpened(), 'Не открывается исходное видео')
        fps = cap.get(cv2.CAP_PROP_FPS); frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        ensure(fps > 0 and frames > 0 and math.isfinite(fps), 'Не определена длительность видео')
        return {'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), 'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                'duration_s': frames / fps}
    finally:
        cap.release()


def file_hash(path):
    hashed = sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''): hashed.update(chunk)
    return hashed.hexdigest()


def source_for_job(job, video):
    source = video_info(video); camera = job.contract['context']['camera']
    ensure(source['width'] == camera['frame_width'] and source['height'] == camera['frame_height'],
           'разрешение видео не соответствует камере задания')
    source['sha256'] = file_hash(video)
    return source


def track_intervals(times, duration, max_gap=1.0):
    times = sorted(set(float(t) for t in times))
    if not times: return []
    out = []; start = previous = times[0]
    for t in times[1:]:
        if t - previous > max_gap:
            # Half-open ranges ending just after the last sample detect simultaneous detections.
            out.append([start, min(duration, previous + 1e-6)]); start = t
        previous = t
    out.append([start, min(duration, previous + 1e-6)])
    return [pair for pair in out if pair[0] < pair[1]]


def package_result(job_path, video_path, artifacts, output_path, *, halves=None, partial_recording=False, understanding=None, evidence_files=None):
    import polars as pl
    from aifootball import schemas
    from aifootball.venue import load_venue
    from aifootball.analytics.report_data import build_report, thumb_request, heatmap_seconds, assign_goalkeeper_teams
    from aifootball.analytics.periods import find_halves, parse_halves, in_period
    from aifootball.analytics.checks import phase1_checks
    from aifootball.report.frames import grab_images
    from tempfile import TemporaryDirectory
    job = read_job(job_path); source = source_for_job(job, video_path)
    artifacts, output_path = Path(artifacts), Path(output_path)
    state = schemas.read(artifacts / 'state.parquet', 'state'); tracks = schemas.read(artifacts / 'tracks.parquet', 'tracks')
    ensure(not state.is_empty() and not tracks.is_empty(), 'Нет обработанных позиций')
    with TemporaryDirectory(prefix='aifootball-cv-') as temporary:
        root = Path(temporary)
        for name, raw in job.files.items(): (root / name).write_bytes(raw)
        venue = load_venue(root)
    times = tracks['ts'].unique().sort().to_list()
    steps = [b - a for a, b in zip(times, times[1:]) if 0 < b - a <= 1]
    step = sorted(steps)[len(steps) // 2] if steps else 1 / venue.target_fps
    end = min(source['duration_s'], times[-1] + step)
    spans = parse_halves(halves, source['duration_s']) if halves else find_halves(tracks)
    spans = [(a, min(b, end)) for a, b in spans] if spans else [(times[0], end)]
    ensure(all(b > a for a, b in spans), 'Нет данных внутри выбранных периодов')
    context = job.contract['context']
    report = build_report(state, tracks, venue, spans,
                          {'A': context['teams']['home']['name'], 'B': context['teams']['away']['name']}, source['duration_s'])
    report['pitch']['orientation'] = 'camera'
    report['match']['video_duration_estimated'] = False
    primary = report['periods'][0]
    # Uniform physical orientation makes maps summable across fragments and halves.
    for period in report['periods']:
        part = in_period(state, period['spans'])
        for player in period['players']:
            player['heatmap_s'] = heatmap_seconds(part.filter(pl.col('track_id') == player['track_id']), venue.length_m, venue.width_m)
        for team, values in period['teams'].items():
            values['heatmap_s'] = heatmap_seconds(part.filter((pl.col('team') == team) & (pl.col('role') == 'player')), venue.length_m, venue.width_m)
    normalize_report(report)
    normalized = assign_goalkeeper_teams(in_period(state, spans), spans, venue.length_m)
    known = {p['track_id']: p for p in primary['players']}
    indexed = []; requests = {}
    for (tid,), group in normalized.group_by('track_id', maintain_order=True):
        player = known.get(tid)
        role = player['role'] if player else group['role'].mode().first()
        team = player['team'] if player else group['team'].mode().first()
        if role not in ('player', 'goalkeeper', 'referee'): role = 'unknown'
        if team not in ('A', 'B'): team = None
        intervals = track_intervals(group['ts'].to_list(), source['duration_s'])
        if not intervals: continue
        request = thumb_request(tracks, tid)
        if request: requests[str(tid)] = request
        indexed.append({'track_id': tid, 'team': team, 'role': role, 'intervals': intervals,
                        'thumb': None, 'has_metrics': tid in known})
    images = grab_images(Path(video_path), requests)
    files = {}
    for track in indexed:
        image = images.get(str(track['track_id']))
        if image:
            name = f"thumbs/{track['track_id']}.jpg"
            files[name] = base64.b64decode(image.split(',', 1)[1]); track['thumb'] = name
    checked = phase1_checks(state, venue.length_m, venue.width_m)
    partial = partial_recording or report['match']['processed_s'] < source['duration_s'] - max(1, step * 2)
    checks = {**checked, 'critical_errors': [] if checked['passed'] else ['Проверки координат/скоростей не пройдены'],
              'partial': partial, 'warnings': ['Частичная запись или неполное покрытие обработки'] if partial else []}
    for name, value in [('report.json', report), ('track-index.json', {'tracks': indexed}), ('checks.json', checks)]:
        files[name] = canonical(value)
    if understanding is not None:
        ensure(isinstance(evidence_files, dict) and len(evidence_files) <= 500, 'Неверный реестр доказательств')
        ensure(all(isinstance(raw, bytes) and len(raw) <= 512 * 1024 for raw in evidence_files.values()), 'Размер доказательства')
        ensure(not (set(files) & set(evidence_files)), 'Конфликт имён доказательств')
        files.update(evidence_files); files['understanding.json'] = canonical(understanding)
        ensure(len(files['understanding.json']) <= 8 * 1024 * 1024, 'Размер understanding.json')
    else:
        ensure(not evidence_files, 'Доказательства требуют understanding')
    manifest = {'contract_version': '2' if understanding is not None else '1', 'run_id': str(uuid4()), 'job_id': job.contract['job_id'],
                'match_id': job.contract['match_id'], 'context_hash': job.contract['context_hash'],
                'camera_profile_id': context['camera']['id'], 'primary_period_key': primary['key'],
                'source_video': source, 'processor': {'name': 'aifootball', 'version': '0.1.0', 'model': venue.model},
                'units': UNITS, 'files': {name: {'size': len(raw), 'sha256': sha256(raw).hexdigest()} for name, raw in files.items()}}
    files['manifest.json'] = canonical(manifest)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = output_path.with_name(output_path.name + '.' + uuid4().hex + '.tmp')
    try:
        with ZipFile(staging, 'w', compression=ZIP_DEFLATED) as archive:
            for name, raw in sorted(files.items()): archive.writestr(name, raw)
        validate_result(staging)
        staging.replace(output_path)
    finally:
        staging.unlink(missing_ok=True)
    print(f'Пакет результата: {output_path}; фрагментов: {len(indexed)}; качество: {checked["passed"]}')
    return output_path


def process_job(job_path, video_path, output_path, *, models=Path('models'), artifacts=None, halves=None,
                partial_recording=False, understand=False, work_dir=None, resume=False, vlm_mode='native',
                vlm_max_requests=200, vlm_max_input_tokens=300_000, vlm_max_output_tokens=100_000,
                analysis_scope='unknown'):
    from aifootball.processor.cv import run_cv
    from aifootball.processor.workspace import Workspace
    ensure(not resume or (work_dir is not None and (Path(work_dir)/'workspace.json').exists()),
           'resume requires an existing --work-dir workspace')
    ensure(vlm_mode in ('native','frames') and analysis_scope in ('full_match','continuous_excerpt','highlights','unknown'), 'Неверные параметры понимания')
    ensure(all(type(value) is int and value >= 0 for value in (vlm_max_requests, vlm_max_input_tokens, vlm_max_output_tokens)), 'Неверный бюджет обработки')
    client = None
    if understand:
        import shutil
        from aifootball.processor.qwen import QwenClient, QwenConfig
        client = QwenClient(QwenConfig.from_env())
        ensure(bool(shutil.which('ffmpeg') and shutil.which('ffprobe')), 'Требуется FFmpeg/ffprobe')
    job = read_job(job_path); source = source_for_job(job, video_path)
    if artifacts is not None:
        meta = load_json((Path(artifacts) / 'meta.json').read_bytes(), 'meta.json')
        ensure(meta.get('camera_profile_id') == job.contract['context']['camera']['id'] and
               meta.get('source_sha256') == source['sha256'] and meta.get('context_hash') == job.contract['context_hash'],
               'Артефакты не подтверждают происхождение камеры/видео/контекста задания')
        if not understand:
            return package_result(job_path, video_path, artifacts, output_path, halves=halves, partial_recording=partial_recording)
    work = Path(work_dir) if work_dir is not None else Path(output_path).parent / ('processor-' + uuid4().hex)
    ensure(not (work_dir is not None and (work/'workspace.json').exists() and not resume), 'Existing work-dir requires --resume')
    workspace = Workspace(work, {'source': source['sha256'], 'context_hash': job.contract['context_hash']})
    with workspace.exclusive():
        root = Path(artifacts) if artifacts is not None else run_cv(Path(job_path), Path(video_path), workspace, models=Path(models))
        understanding = None; evidence = None
        if understand:
            from aifootball.processor.understand import run_understanding
            from aifootball.processor.budget import Budget
            budget = Budget(workspace, max_requests=vlm_max_requests, max_input_tokens=vlm_max_input_tokens,
                            max_output_tokens=vlm_max_output_tokens)
            understanding, evidence = run_understanding(job, Path(video_path), root, workspace, client=client,
                budget=budget, mode=vlm_mode, analysis_scope=analysis_scope)
        return package_result(job_path, video_path, root, output_path, halves=halves,
            partial_recording=partial_recording, understanding=understanding, evidence_files=evidence)



def normalize_report(report):
    """Translate legacy report missingness into the strict exchange contract."""
    metrics = ['observed_s','distance_m','m_per_min','hsr_m','sprints','vmax_ms','heatmap_s']
    for period in report['periods']:
        for player in period['players']:
            notes = player.setdefault('metric_notes', {})
            for key in metrics:
                if player.get(key) is None:
                    notes[key] = 'Нет устойчивых измерений скорости' if key == 'vmax_ms' else 'Недостаточно наблюдений фрагмента'
        for team in period['teams'].values():
            notes = team.setdefault('metric_notes', {})
            if not team.get('observed_s'):
                team['low_data'] = True
                for key in metrics + ['width_m','depth_m','compactness_m2']:
                    team[key] = None
                    notes[key] = 'Нет наблюдений команды'
            else:
                for key in metrics + ['width_m','depth_m','compactness_m2']:
                    if key in team and team[key] is None: notes[key] = 'Недостаточно наблюдений команды'
