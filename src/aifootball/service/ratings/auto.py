"""Автоматические версии участия и действий для оценок — из подтверждённого видеоанализа.

Подтверждая видеоанализ, администратор подтверждает и сопоставление фрагментов с игроками состава.
Из этого без ручной разметки получаются две подтверждённые версии с источником cv_auto:

- участие — время на площадке по фрагментам, назначенным игроку. Разрыв между его фрагментами
  до GAP_FILL_S — обрыв трекера в толпе или у края кадра, а не замена (тот же предел, что у склейки
  треков); разрыв не заполняется, если на площадке оказалось бы больше игроков команды, чем
  разрешает регламент. База времени — «время присутствия с паузами»: мяч в игре видео не размечает.
  Роли не назначаются: амплуа по видео неизвестно.
- действия — события по мячу из пакета (сейчас только передачи: остальные виды не прошли порог
  точности). Автор и адресат — игроки назначенных фрагментов, иначе «неизвестен». Полнота
  категории — partial: распознаётся не каждая передача.

Ручная версия главнее автоматической (inputs.selected_inputs). Методика оценки не меняется:
по неполной категории показатель в оценку не входит, минуты и известные действия видны в разборе.
"""
from collections import defaultdict
from math import ceil, floor
from uuid import NAMESPACE_URL, UUID, uuid5
from pydantic import ValidationError
from sqlalchemy import select, func, update
from aifootball.analytics.track_groups import MAX_GAP_S
from aifootball.service.analysis.models import AnalysisAssignment
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.matches.operations import get_match_view
from aifootball.service.protocol.models import ProtocolVersion
from aifootball.service.ratings.models import (AUTO_SOURCE, ActionVersion, ParticipationVersion, RatingMatchPublication,
                                               TournamentRatingState, is_auto)

GAP_FILL_S = MAX_GAP_S
AUTO_CATEGORIES = {'pass': 'passes'}  # вид события по мячу -> категория полноты действий


def _merge(spans, gap_ms=0):
    out = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1] + gap_ms:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _excess(group, limit):
    """Отрезки, где на площадке одновременно больше limit игроков одной команды."""
    deltas = defaultdict(int)
    for spans in group.values():
        for a, b in spans:
            deltas[a] += 1
            deltas[b] -= 1
    out, count, start = [], 0, None
    for t in sorted(deltas):
        count += deltas[t]
        if count > limit and start is None:
            start = t
        elif count <= limit and start is not None:
            out.append((start, t))
            start = None
    return out


def _cut(spans, a, b):
    return [piece for s, e in spans for piece in ([s, min(e, a)], [max(s, b), e]) if piece[0] < piece[1]]


def _trim(group, limit):
    """Лишний игрок на площадке — дубль при замене или ошибка назначения: отрезок снимается с того,
    чей фрагмент начинается или кончается ближе всего к перебору (край передачи между игроками)."""
    for _ in range(10000):
        excess = _excess(group, limit)
        if not excess:
            return
        a, b = excess[0]
        edge = lambda pid: min(min(abs(s - a), abs(e - b)) for s, e in group[pid] if s < b and e > a)
        pid = min((p for p in group if any(s < b and e > a for s, e in group[p])), key=lambda p: (edge(p), p))
        group[pid] = _cut(group[pid], a, b)


def _fill(group, limit, gap_ms):
    """Короткие разрывы — время на площадке, если это не даёт перебора игроков; сначала самые короткие."""
    gaps = sorted((b0 - a1, pid, a1, b0) for pid, spans in group.items()
                  for (_, a1), (b0, _) in zip(spans, spans[1:]) if b0 - a1 <= gap_ms)
    for _, pid, a, b in gaps:
        before = group[pid]
        group[pid] = _merge(before + [[a, b]])
        if _excess(group, limit):
            group[pid] = before


def presence(tracks, assigned, sides, duration_ms, limit, gap_s=GAP_FILL_S):
    """Игрок -> отрезки на площадке, мс. tracks: трек -> индекс трека, assigned: трек -> игрок, sides: игрок -> сторона."""
    raw = defaultdict(list)
    for tid, pid in assigned.items():
        for start, end in tracks[tid]['intervals']:
            a, b = max(0, floor(start * 1000)), min(duration_ms, ceil(end * 1000))
            if a < b:
                raw[pid].append([a, b])
    people = {pid: _merge(spans) for pid, spans in raw.items()}
    for side in sorted(set(sides.values())):
        group = {pid: spans for pid, spans in people.items() if sides[pid] == side}
        _trim(group, limit)
        _fill(group, limit, round(gap_s * 1000))
        people.update(group)
    return {pid: spans for pid, spans in people.items() if spans}


def video_scope(run):
    scope = ((run.understanding or {}).get('source') or {}).get('analysis_scope')
    if scope in ('full_match', 'continuous_excerpt', 'highlights'):
        return scope
    return 'continuous_excerpt' if run.checks.get('partial') else 'full_match'


def participation_document(run, job, lineup, protocol_id, assigned, players_on_pitch):
    duration = round(run.manifest['source_video']['duration_s'] * 1000)
    video = {p['player_id']: p['side'] for p in job.context['rosters']}
    sides = {p['player_id']: p['side'] for p in lineup if video.get(p['player_id']) == p['side']}
    tracks = {t['track_id']: t for t in run.tracks['tracks']}
    people = presence(tracks, {tid: pid for tid, pid in assigned.items() if pid in sides and tid in tracks}, sides,
                      duration, players_on_pitch)
    players = [{'player_id': pid, 'presence': people[pid], 'completeness': 'complete', 'appeared': True, 'roles': []}
               if pid in people else {'player_id': pid, 'presence': None, 'completeness': 'unknown', 'appeared': None, 'roles': []}
               for pid in sides]
    return {'clock_basis': 'video', 'time_basis': 'running_clock', 'analysis_scope': video_scope(run), 'duration_ms': duration,
            'source_analysis_run_id': str(run.id), 'source_protocol_version_id': protocol_id,
            'initial_five': {'home': [], 'away': []}, 'players': players, 'play_intervals': None,
            'possession_intervals': {'home': None, 'away': None}, 'manpower': [],
            'notes': 'Автоматически по видео: время на площадке по фрагментам, назначенным игрокам.'}


def actions_document(run, job, part, assigned):
    """Передачи прогона как действия игроков; события без назначенного фрагмента — с неизвестным автором."""
    doc = part.document; duration = doc['duration_ms']
    sides = {p['player_id']: p['side'] for p in part.lineup}
    on_pitch = {p['player_id']: p['presence'] or [] for p in doc['players']}
    pitch = job.context['pitch']
    point = lambda xy: [min(max(float(xy[0]), 0.0), float(pitch['length_m'])), min(max(float(xy[1]), 0.0), float(pitch['width_m']))]
    events = run.events or {}
    kinds = [k for k in events.get('kinds', []) if k in AUTO_CATEGORIES]
    actions = []
    for index, e in enumerate(events.get('events', [])):
        side = run.side_map.get(e.get('team'))
        if e['kind'] not in kinds or side is None:
            continue
        start = max(0, round(e['start_s'] * 1000)); end = max(start, round(e['end_s'] * 1000))
        if end >= duration:
            continue
        author = assigned.get(e['track_id'])
        if author is not None and (sides.get(author) != side or not any(a <= start < b for a, b in on_pitch.get(author, []))):
            author = None
        recipient = assigned.get(e.get('recipient_track_id')) if e['success'] else None
        if recipient is not None and (recipient == author or sides.get(recipient) != side):
            recipient = None
        actions.append({'id': str(uuid5(NAMESPACE_URL, f'aifootball:cv-auto:{run.id}:{index}')), 'kind': e['kind'],
                        'player_id': author, 'recipient_id': recipient, 'opponent_id': None, 'side': side, 'role': None,
                        'start_ms': start, 'end_ms': end, 'success': bool(e['success']), 'on_target': None,
                        'outcome': 'success' if e['success'] else 'failure', 'possession_id': None,
                        'start_xy': point(e['start_xy']), 'end_xy': point(e['end_xy']), 'attacking_direction': 'unknown',
                        'penalty_conceded': False, 'source_episode_id': None, 'source_video_ms': None, 'shot_id': None,
                        'decision': 'accepted', 'notes': ''})
    primary = next(p for p in run.report['periods'] if p['key'] == run.manifest['primary_period_key'])
    spans = _merge([[max(0, floor(a * 1000)), min(duration, ceil(b * 1000))] for a, b in primary['spans'] if a < b])
    spans = [s for s in spans if s[0] < s[1]]
    completeness = {AUTO_CATEGORIES[k]: [{'status': 'partial', 'intervals': spans, 'player_ids': None}] for k in kinds} if spans else {}
    return {'clock_basis': 'video', 'analysis_scope': doc['analysis_scope'], 'duration_ms': duration,
            'source_participation_version_id': str(part.id), 'source_analysis_run_id': str(run.id),
            'source_protocol_version_id': doc['source_protocol_version_id'], 'actions': actions, 'links': [],
            'completeness': completeness,
            'notes': 'Автоматически по видео: передачи по мячу; распознаётся не каждая передача.'}


def _existing(db, run, protocol_id):
    parts = db.scalars(select(ParticipationVersion).where(ParticipationVersion.source_analysis_run_id == run.id,
                                                         ParticipationVersion.status == 'confirmed')
                       .order_by(ParticipationVersion.revision.desc())).all()
    part = next((v for v in parts if is_auto(v) and v.source_protocol_version_id == protocol_id), None)
    action = db.scalar(select(ActionVersion).where(ActionVersion.source_participation_version_id == part.id)
                       .order_by(ActionVersion.revision.desc()).limit(1)) if part else None
    return part, action if is_auto(action) else None


def _attempt(db, build):
    """Сохранение в точке отката: ошибка данных видео не отменяет подтверждение или публикацию."""
    try:
        with db.begin_nested():
            return build(), None
    except DomainError as exc:
        return None, exc.message
    except (ValidationError, ValueError) as exc:
        return None, f'Данные видео не прошли проверку: {exc}'[:300]


def ensure_auto_versions(db, match, run, job, actor_id, protocol_id):
    """Автоматические участие и действия прогона для версии протокола; созданные ранее не повторяются.
    Возвращает (участие, действия, причина): причина — почему версии не собраны, иначе None."""
    from aifootball.service.ratings.actions import save_actions
    from aifootball.service.ratings.operations import save_participation
    from aifootball.service.ratings.schemas import ActionsSave, ParticipationSave
    part, action = _existing(db, run, protocol_id)
    assigned = {a.track_id: str(a.player_id) for a in db.scalars(select(AnalysisAssignment).where(
        AnalysisAssignment.run_id == run.id, AnalysisAssignment.player_id.is_not(None)))}
    note = None
    if part is None:
        protocol = get_entity(db, ProtocolVersion, protocol_id) if protocol_id else None
        view = None if protocol else get_match_view(db, match.id)
        lineup = protocol.snapshot['lineup'] if protocol else view['lineup']
        rules = protocol.snapshot['regulation']['rules'] if protocol else view['regulation']['rules']
        doc = participation_document(run, job, lineup, str(protocol_id) if protocol_id else None, assigned, rules['players_on_pitch'])
        if not any(p['presence'] for p in doc['players']):
            return None, None, 'Ни одному игроку протокола не назначен фрагмент записи'

        def build_participation():
            latest = db.scalar(select(func.max(ParticipationVersion.revision)).where(ParticipationVersion.match_id == match.id)) or 0
            saved = save_participation(db, match.id, actor_id, ParticipationSave(
                request_id=uuid5(NAMESPACE_URL, f'aifootball:auto-participation:{run.id}:{protocol_id}'),
                expected_revision=latest, expected_match_revision=match.revision, status='confirmed', document=doc),
                source_kind=AUTO_SOURCE)
            return db.get(ParticipationVersion, UUID(str(saved['id'])))
        part, note = _attempt(db, build_participation)
        if part is None:
            return None, None, note
    if action is None and run.events:
        def build_actions():
            latest = db.scalar(select(func.max(ActionVersion.revision)).where(ActionVersion.match_id == match.id)) or 0
            saved = save_actions(db, match.id, actor_id, ActionsSave(
                request_id=uuid5(NAMESPACE_URL, f'aifootball:auto-actions:{part.id}'),
                expected_revision=latest, expected_match_revision=match.revision, status='confirmed',
                document=actions_document(run, job, part, assigned)), source_kind=AUTO_SOURCE)
            return db.get(ActionVersion, UUID(str(saved['id'])))
        action, note = _attempt(db, build_actions)
    return part, action, note


def latest_protocol_id(db, match_id):
    return db.scalar(select(ProtocolVersion.id).where(ProtocolVersion.match_id == match_id)
                     .order_by(ProtocolVersion.number.desc()).limit(1))


def confirm_auto_sources(db, match, run, job, actor_id):
    """При подтверждении видеоанализа — версии для оценок в кабинете (по последней версии протокола)."""
    return ensure_auto_versions(db, match, run, job, actor_id, latest_protocol_id(db, match.id))[2]


def publish_auto_sources(db, match, run, job, actor_id):
    """Опубликованный видеоанализ становится источником оценок на сайте, если вручную не выбраны другие версии."""
    pub = db.scalar(select(RatingMatchPublication).where(RatingMatchPublication.match_id == match.id))
    chosen = [db.get(model, value) for model, value in ((ParticipationVersion, pub.participation_version_id),
                                                        (ActionVersion, pub.action_version_id)) if value] if pub else []
    if any(not is_auto(v) for v in chosen):
        return None
    part = action = note = None
    if match.published_version_id is None:
        note = 'Протокол матча не опубликован'
    else:
        part, action, note = ensure_auto_versions(db, match, run, job, actor_id, match.published_version_id)
    target = (part.id if part else None, action.id if action else None)
    current = (pub.participation_version_id, pub.action_version_id) if pub else (None, None)
    if current == target:
        return note
    if pub is None:
        pub = RatingMatchPublication(match_id=match.id, created_by=actor_id, revision=0)
        db.add(pub)
    pub.participation_version_id, pub.action_version_id = target
    pub.revision += 1
    # Источники рейтинга изменились: прежний расчёт для сайта устареет по отпечатку, ревизия — для открытых страниц.
    db.execute(update(TournamentRatingState).where(TournamentRatingState.tournament_id == match.tournament_id)
               .values(revision=TournamentRatingState.revision + 1))
    db.flush()
    return note


def auto_sources_view(db, run):
    """Последние автоматические версии прогона для экрана видеоанализа."""
    part = db.scalar(select(ParticipationVersion).where(ParticipationVersion.source_analysis_run_id == run.id,
                                                       ParticipationVersion.provenance['source_kind'].astext == AUTO_SOURCE)
                     .order_by(ParticipationVersion.revision.desc()).limit(1))
    if part is None:
        return None
    action = db.scalar(select(ActionVersion).where(ActionVersion.source_participation_version_id == part.id,
                                                   ActionVersion.provenance['source_kind'].astext == AUTO_SOURCE)
                       .order_by(ActionVersion.revision.desc()).limit(1))
    players = sum(1 for p in part.document['players'] if p['presence'])
    return {'participation_version_id': part.id, 'participation_revision': part.revision, 'players': players,
            'action_version_id': action.id if action else None, 'action_revision': action.revision if action else None,
            'passes': sum(1 for a in action.document['actions'] if a['kind'] == 'pass') if action else 0}
