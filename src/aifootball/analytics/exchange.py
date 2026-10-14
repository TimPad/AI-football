"""Versioned, bounded exchange contract. No CV/model/service imports."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZipFile, BadZipFile
import json
import math
import re
import stat

UNITS = {'distance': 'm', 'speed': 'm/s', 'time': 's', 'heatmap': 's'}
RESULT_JSON = {'manifest.json', 'report.json', 'track-index.json', 'checks.json'}
JOB_FILES = {'job.json', 'venue.yaml', 'homography.json', 'pitch_polygon.json', 'calib.json', 'source.json'}


class ExchangeError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    compressed: int = 100 * 1024 * 1024
    unpacked: int = 300 * 1024 * 1024
    files: int = 2048
    json: int = 64 * 1024 * 1024
    thumb: int = 2 * 1024 * 1024


@dataclass(frozen=True)
class ValidatedResult:
    manifest: dict
    report: dict
    tracks: dict
    checks: dict
    files: dict[str, bytes]
    content_hash: str


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def ensure(condition, message):
    if not condition:
        raise ExchangeError(message)


def numeric(value, label, *, maximum=1e9, minimum=0):
    ensure(type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum,
           f'Недопустимое числовое значение: {label}')
    return value


def uuid(value, label):
    try:
        ensure(isinstance(value, str) and str(UUID(value)) == value, f'Неверный UUID: {label}')
    except (ValueError, TypeError, AttributeError):
        raise ExchangeError(f'Неверный UUID: {label}') from None


def hash_value(value, label):
    ensure(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value), f'Неверный SHA256: {label}')


def load_json(raw, label):
    def pairs(items):
        out = {}
        for key, value in items:
            ensure(key not in out, f'Повторяющийся ключ JSON: {label}')
            out[key] = value
        return out
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ExchangeError(f'NaN/Infinity: {label}')))
        def finite(item, depth=0):
            ensure(depth <= 32, 'Слишком глубокая структура JSON')
            if isinstance(item, dict):
                for key, v in item.items():
                    ensure(len(key) <= 500, 'Слишком длинный ключ JSON'); finite(v, depth + 1)
            elif isinstance(item, list):
                for v in item: finite(v, depth + 1)
            elif type(item) in (float, int):
                ensure(math.isfinite(item), f'NaN/Infinity: {label}')
            elif isinstance(item, str):
                ensure(len(item) <= 10000, 'Слишком длинное текстовое поле JSON')
        finite(value)
        ensure(isinstance(value, dict), f'Ожидается объект JSON: {label}')
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise ExchangeError(f'Не читается JSON: {label}') from exc


def read_archive(source, limits=Limits(), *, job=False):
    if isinstance(source, (str, Path)):
        ensure(Path(source).stat().st_size <= limits.compressed, 'Превышен размер ZIP')
        source = Path(source).read_bytes()
    ensure(isinstance(source, bytes) and len(source) <= limits.compressed, 'Превышен размер ZIP')
    files = {}; total = 0
    try:
        with ZipFile(BytesIO(source)) as archive:
            ensure(len(archive.infolist()) <= limits.files, 'Превышено число файлов ZIP')
            for info in archive.infolist():
                name = info.filename
                allowed = name in JOB_FILES if job else name in RESULT_JSON or bool(re.fullmatch(r'thumbs/[A-Za-z0-9_-]{1,100}\.jpg', name))
                ensure(allowed and name not in files and not info.is_dir(), f'Недопустимый файл ZIP: {name[:100]}')
                ensure(not stat.S_ISLNK(info.external_attr >> 16) and not (info.flag_bits & 1), 'Ссылки/зашифрованные файлы запрещены')
                cap = limits.thumb if name.endswith('.jpg') else limits.json
                ensure(info.file_size <= cap and total + info.file_size <= limits.unpacked, 'Превышен распакованный размер ZIP')
                with archive.open(info) as stream:
                    raw = stream.read(min(cap, limits.unpacked - total) + 1)
                ensure(len(raw) <= cap and total + len(raw) <= limits.unpacked, 'Превышен распакованный размер ZIP')
                ensure(len(raw) == info.file_size, 'Размер файла ZIP не совпадает')
                total += len(raw); files[name] = raw
    except (BadZipFile, RuntimeError, OSError, EOFError, NotImplementedError) as exc:
        raise ExchangeError('Не читается ZIP или нарушена его целостность') from exc
    return files


def intervals(values, duration, label):
    ensure(isinstance(values, list) and 0 < len(values) <= 100000, f'Нет интервалов: {label}')
    previous = -1
    for pair in values:
        ensure(isinstance(pair, list) and len(pair) == 2, f'Неверный интервал: {label}')
        start, end = pair
        numeric(start, label, maximum=duration + .001); numeric(end, label, maximum=duration + .001)
        ensure(start < end and start >= previous, f'Пересечение или порядок интервалов: {label}')
        previous = end
    return sum(end - start for start, end in values)


def heatmap(value, pitch, label):
    if value is None:
        return
    rows, cols = math.ceil(pitch['length_m'] / pitch['cell_m']), math.ceil(pitch['width_m'] / pitch['cell_m'])
    ensure(isinstance(value, list) and len(value) == rows, f'Размер тепловой карты: {label}')
    for row in value:
        ensure(isinstance(row, list) and len(row) == cols, f'Размер тепловой карты: {label}')
        for item in row: numeric(item, label)


def validate_result(source, limits=Limits()):
    files = read_archive(source, limits)
    ensure(RESULT_JSON <= set(files), 'Пакет должен содержать manifest.json, report.json, track-index.json и checks.json')
    manifest = load_json(files['manifest.json'], 'manifest.json')
    report = load_json(files['report.json'], 'report.json')
    tracks = load_json(files['track-index.json'], 'track-index.json')
    checks = load_json(files['checks.json'], 'checks.json')
    try:
        ensure(manifest['contract_version'] == '1' and report['schema_version'] == '1', 'Неподдерживаемая версия контракта')
        for key in ['run_id', 'job_id', 'match_id', 'camera_profile_id']: uuid(manifest[key], key)
        hash_value(manifest['context_hash'], 'context_hash')
        ensure(manifest['units'] == UNITS, 'Несовместимые единицы измерения')
        source_video = manifest['source_video']; duration = numeric(source_video['duration_s'], 'duration_s', minimum=.001, maximum=86400)
        hash_value(source_video['sha256'], 'video SHA256')
        for dimension in ['width', 'height']:
            ensure(type(source_video[dimension]) is int, 'Разрешение должно быть целым'); numeric(source_video[dimension], dimension, minimum=1, maximum=32768)
        ensure(isinstance(manifest['processor'], dict) and all(isinstance(manifest['processor'][k], str) and manifest['processor'][k] for k in ['name', 'version', 'model']), 'Нет версии обработчика/модели')
        ensure(set(manifest['files']) == set(files) - {'manifest.json'}, 'Перечень файлов не совпадает с ZIP')
        for name, item in manifest['files'].items():
            ensure(item['size'] == len(files[name]) and item['sha256'] == sha256(files[name]).hexdigest(), f'Целостность файла: {name}')
        for name, raw in files.items():
            if name.endswith('.jpg'):
                from PIL import Image
                with Image.open(BytesIO(raw)) as image:
                    ensure(image.format == 'JPEG' and image.width * image.height <= 4000000, 'Неверная миниатюра')
                    image.verify()
        pitch = report['pitch']
        for key in ['length_m', 'width_m']: numeric(pitch[key], key, minimum=.01, maximum=300)
        ensure(pitch['cell_m'] == 1, 'Размер ячейки карты должен быть 1 метр')
        ensure(pitch.get('orientation', 'camera') == 'camera', 'Карты должны использовать координаты площадки')
        numeric(report['match']['processed_s'], 'processed_s', maximum=duration + .1)
        ensure(abs(report['match']['video_s'] - duration) <= .1, 'Длительность отчёта не совпадает с источником')
        ensure(isinstance(tracks['tracks'], list) and len(tracks['tracks']) <= 50000, 'Неверный индекс треков')
        index = {}
        for track in tracks['tracks']:
            tid = track['track_id']; ensure(type(tid) is int and 0 <= tid <= 2147483647 and tid not in index, 'Повторяющийся/неверный track_id')
            ensure(track['team'] in ('A', 'B', None) and track['role'] in ('player', 'goalkeeper', 'referee', 'unknown'), 'Неверная команда/роль трека')
            intervals(track['intervals'], duration, f'трек {tid}')
            ensure(type(track['has_metrics']) is bool, 'Неверный признак метрик')
            thumb = track.get('thumb'); ensure(thumb is None or (isinstance(thumb, str) and thumb in files and thumb.startswith('thumbs/')), 'Нет миниатюры в пакете')
            index[tid] = track
        ensure(isinstance(report['periods'], list) and 0 < len(report['periods']) <= 20, 'Неверное число периодов')
        keys = set(); primary = None
        for period in report['periods']:
            key = period['key']; ensure(isinstance(key, str) and key not in keys and len(key) <= 50, 'Повторяющийся период'); keys.add(key)
            ensure(isinstance(period['name'], str) and 0 < len(period['name'].strip()) <= 200, 'Нет названия периода')
            span_s = intervals(period['spans'], duration, key)
            ensure(abs(numeric(period['duration_s'], 'period duration') - span_s) <= .11, 'Длительность периода не совпадает с интервалами')
            seen = set()
            for player in period['players']:
                ensure(isinstance(player['label'], str) and 0 < len(player['label'].strip()) <= 200, 'Нет подписи фрагмента')
                tid = player['track_id']; ensure(tid in index and tid not in seen, 'Метрика ссылается на неизвестный/повторный трек'); seen.add(tid)
                ensure(player['team'] == index[tid]['team'] and player['role'] == index[tid]['role'], 'Команда/роль метрики не совпадает с треком')
                for metric in ['observed_s', 'distance_m', 'm_per_min', 'hsr_m', 'sprints', 'vmax_ms']:
                    ensure(metric in player, f'Нет поля {metric}')
                    if player[metric] is not None: numeric(player[metric], metric)
                    else: ensure(isinstance(player.get('metric_notes', {}).get(metric), str), f'Нет причины отсутствия {metric}')
                if player['observed_s'] is not None:
                    ensure(player['observed_s'] <= span_s + .11, 'Время игрока превышает период')
                    visible = sum(max(0, min(b,d)-max(a,c)) for a,b in index[tid]['intervals'] for c,d in period['spans'])
                    ensure(player['observed_s'] <= visible + .11 * len(index[tid]['intervals']), 'Время игрока превышает интервалы трека')
                if player['vmax_ms'] is not None: ensure(player['vmax_ms'] <= 30, 'Скорость превышает допустимый диапазон')
                if player['distance_m'] is not None and player['observed_s'] is not None:
                    ensure(player['distance_m'] <= player['observed_s'] * 30 + 1, 'Дистанция превышает допустимый диапазон')
                if player['hsr_m'] is not None and player['distance_m'] is not None:
                    ensure(player['hsr_m'] <= player['distance_m'] + .2, 'HSR превышает дистанцию')
                if player['sprints'] is not None: ensure(type(player['sprints']) is int, 'Число спринтов должно быть целым')
                ensure('heatmap_s' in player, 'Нет тепловой карты'); heatmap(player['heatmap_s'], pitch, f'трек {tid}')
            for side, team in period.get('teams', {}).items():
                ensure(side in ('A','B'), 'Неверная команда периода')
                for metric in ['observed_s','distance_m','m_per_min','hsr_m','sprints','width_m','depth_m','compactness_m2']:
                    if team.get(metric) is not None: numeric(team[metric], 'командная '+metric)
                if 'heatmap_s' in team: heatmap(team['heatmap_s'], pitch, 'команда')
            if key == manifest['primary_period_key']: primary = period
        ensure(primary is not None, 'Нет основного периода')
        primary_ids = {p['track_id'] for p in primary['players']}
        for tid, track in index.items():
            ensure(track['has_metrics'] == (tid in primary_ids), 'Индекс не совпадает с метриками основного периода')
        ensure(type(checks['passed']) is bool and type(checks['partial']) is bool,
               'Нет признаков качества и полноты')
        ensure(checks['partial'] or report['match']['processed_s'] >= duration - 1, 'Неполное покрытие должно быть помечено как частичное')
        ensure(isinstance(checks['critical_errors'], list) and isinstance(checks['warnings'], list) and
               all(isinstance(x, str) for x in checks['critical_errors'] + checks['warnings']), 'Неверные проверки качества')
    except (KeyError, TypeError, AttributeError, ValueError, OSError) as exc:
        if isinstance(exc, ExchangeError): raise
        raise ExchangeError('Структура или содержимое пакета не соответствует контракту') from exc
    content_hash = sha256(canonical({'manifest': manifest, 'files': {name: sha256(raw).hexdigest() for name, raw in sorted(files.items()) if name != 'manifest.json'}})).hexdigest()
    return ValidatedResult(manifest, report, tracks, checks, files, content_hash)
