"""Публичный рейтинг матча по действиям: голы, ассисты и карточки — из опубликованного протокола, удары
и защита — из подтверждённой разметки (или опубликованной ручной версии действий), передачи — из публичной
сводки, вратари и время на площадке — из участия, иначе вратарь — по амплуа в каталоге, если он один.

Пока авторов меньше доли goal_authors_min голов, оценки не показываются: без авторов рейтинг матча
описывает разметку, а не игроков."""

from sqlalchemy import select

from aifootball.ratings.match_points import load_policy, match_points
from aifootball.service.errors import DomainError
from aifootball.service.matches.models import Match
from aifootball.service.public_visibility import require_public_match
from aifootball.service.ratings.models import ActionVersion, ParticipationVersion, RatingMatchPublication, is_auto
from aifootball.service.ratings.team_stats import (
    TAGGED_CATEGORIES,
    _analysis_run,
    _tagged_records,
    _tagged_version,
    public_action_stats,
)

ACTION_KINDS = ('shot', 'duel', 'recovery', 'shot_block', 'save')
CATEGORIES = (*TAGGED_CATEGORIES, 'passes')


def _participation(db, match, pub):
    """Опубликованная версия участия; иначе последняя ручная; иначе автоматическая опубликованного прогона."""
    if pub and pub.participation_version_id:
        return db.get(ParticipationVersion, pub.participation_version_id)
    versions = list(
        db.scalars(
            select(ParticipationVersion)
            .where(ParticipationVersion.match_id == match.id, ParticipationVersion.status == 'confirmed')
            .order_by(ParticipationVersion.revision)
        )
    )
    manual = [v for v in versions if not is_auto(v)]
    auto = [v for v in versions if is_auto(v) and v.source_analysis_run_id == match.published_analysis_run_id]
    return (manual or auto or [None])[-1]


def _actions_version(db, match, pub, run):
    version = db.get(ActionVersion, pub.action_version_id) if pub and pub.action_version_id else None
    if version is not None and not is_auto(version):
        return version
    return _tagged_version(db, match.id, run) if run is not None else None


def _period_offsets(rules):
    periods = rules['periods_s'] + (rules['extra']['periods_s'] if rules['extra']['enabled'] else [])
    offsets, cursor = {}, 0
    for index, seconds in enumerate(periods, 1):
        offsets[index] = cursor
        cursor += seconds * 1000
    return offsets


def _goalkeepers(db, lineup, part):
    from aifootball.service.catalog.models import Player

    side_of = {p['player_id']: p['side'] for p in lineup}
    result = {'home': [], 'away': []}
    for person in (part.document.get('players') or []) if part else []:
        pid = str(person['player_id'])
        spans = [s for r in person.get('roles') or [] if r['role'] == 'goalkeeper' for s in r['intervals']]
        if pid in side_of and spans:
            result[side_of[pid]].append({'player_id': pid, 'intervals': spans})
    for side in result:
        if result[side]:
            continue
        ids = [pid for pid, s in side_of.items() if s == side]
        keepers = list(db.scalars(select(Player.id).where(Player.id.in_(ids), Player.position == 'goalkeeper')))
        if len(keepers) == 1:
            result[side] = [{'player_id': str(keepers[0]), 'intervals': None}]
    return result


def _public_passes(db, match_id):
    """Передачи по игрокам и полнота категорий — как в публичной сводке действий."""
    try:
        stats = public_action_stats(db, match_id)
    except DomainError:
        return {}, {}
    passes = {str(r['player_id']): r['total'] for r in stats.get('pass_players') or [] if r.get('player_id')}
    return passes, stats.get('coverage') or {}


def public_match_points(db, match_id):
    require_public_match(db, match_id)
    match = db.get(Match, match_id)
    from aifootball.service.protocol.models import ProtocolVersion

    protocol = db.get(ProtocolVersion, match.published_version_id) if match.published_version_id else None
    if protocol is None:
        raise DomainError('not_found', 'Протокол матча не опубликован', status=404)
    snapshot = protocol.snapshot
    lineup = [
        {'player_id': str(p['player_id']), 'side': p['side'], 'display_name': p.get('display_name')}
        for p in snapshot['lineup']
    ]
    pub = db.scalar(select(RatingMatchPublication).where(RatingMatchPublication.match_id == match_id))
    run = _analysis_run(db, match.published_analysis_run_id)
    version = _actions_version(db, match, pub, run)
    part = _participation(db, match, pub)
    clock = part.document['clock_basis'] if part else None
    action_clock = version.document['clock_basis'] if version else None
    canonical = (version.canonical_actions or []) if version else []
    # Время на часах участия: те же часы — как есть; игровые часы участия и разметка по видео — через таймы записи.
    converted = {}
    if clock == 'game' and action_clock == 'video' and run is not None:
        converted = {r['id']: r['match_ms'] for r in _tagged_records(version, run, 'all')}

    def moment(record):
        if record.get('start_ms') is None:
            return None
        if clock is None or record.get('clock_basis', action_clock) == clock:
            return record['start_ms']
        return converted.get(record['id'])

    offsets = _period_offsets(snapshot['regulation']['rules'])
    canonical_goals = {r.get('canonical_event_id') or r['id']: r for r in canonical if r['kind'] == 'goal'}
    goals, cards = [], []
    for e in snapshot['protocol']['events']:
        if e['kind'] == 'card':
            cards.append({'player_id': e.get('player_id'), 'card': e['card']})
        if e['kind'] != 'goal' or e.get('side') not in ('home', 'away'):
            continue
        t = None
        linked = canonical_goals.get(e['id'])
        if linked is not None and clock is not None:
            t = moment(linked)
        if t is None and clock == 'game' and e.get('period') in offsets and e.get('elapsed_ms') is not None:
            t = offsets[e['period']] + e['elapsed_ms']
        goals.append(
            {
                'id': e['id'],
                'side': e['side'],
                'player_id': e.get('player_id'),
                'assist_id': e.get('assist_id'),
                'own_goal': bool(e.get('own_goal')),
                't': t,
            }
        )
    actions = [
        {
            'kind': r['kind'],
            'side': r.get('side'),
            'player_id': r.get('player_id'),
            'on_target': r.get('on_target'),
            'outcome': r.get('outcome'),
            'success': r.get('success'),
            'at': r.get('start_ms'),
            't': moment(r) if clock is not None else None,
        }
        for r in canonical
        if r['kind'] in ACTION_KINDS and r.get('side') in ('home', 'away')
    ]
    presence = {}
    for person in (part.document.get('players') or []) if part else []:
        if person.get('presence') is not None:
            presence[str(person['player_id'])] = person['presence']
    passes, coverage = _public_passes(db, match_id)
    partial = [c for c in CATEGORIES if coverage.get(c, 'unknown') != 'complete']
    policy = load_policy()
    result = match_points(
        lineup=lineup,
        goals=goals,
        cards=cards,
        actions=actions,
        passes=passes,
        goalkeepers=_goalkeepers(db, lineup, part),
        presence=presence,
        partial=partial,
        policy=policy,
    )
    if not result['ready']:
        result['items'], result['best_player_id'] = [], None
    # Время на площадке из автоматической версии — это фрагменты видео: на трансляции — время в кадре.
    result['on_court_source'] = None if not presence else 'video' if is_auto(part) else 'manual'
    result['policy'] = {k: policy[k] for k in ('base', 'min', 'max', 'pass_cap', 'goal_authors_min', 'points')}
    return result
