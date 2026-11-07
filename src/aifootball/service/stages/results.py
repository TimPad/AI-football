"""Результаты матчей для таблиц: кабинет — последняя подтверждённая версия, зритель — опубликованная."""
from sqlalchemy import select, func, and_
from aifootball.service.matches.models import Match
from aifootball.service.protocol.models import ProtocolVersion
from aifootball.service.stages.rules.progress import Leg


def leg_from_snapshot(snapshot):
    score = snapshot['projection']['effective_score']
    if score.get('home') is None or score.get('away') is None: return None
    pens = (snapshot.get('protocol') or {}).get('shootout_totals') or {}
    points = snapshot['regulation']['rules']['points']
    return Leg(str(snapshot['home_entry_id']), str(snapshot['away_entry_id']), score['home'], score['away'],
               pens.get('home'), pens.get('away'), (points['win'], points['draw'], points['loss']))


def load_results(db, match_ids, scope):
    """{match_id: Leg}; отменённые матчи и матчи без полного счёта не учитываются."""
    ids = list({mid for mid in match_ids if mid})
    if not ids: return {}
    if scope == 'public':
        query = (select(Match.id, ProtocolVersion.snapshot)
                 .join(ProtocolVersion, Match.published_version_id == ProtocolVersion.id))
    else:
        latest = (select(ProtocolVersion.match_id, func.max(ProtocolVersion.number).label('number'))
                  .where(ProtocolVersion.match_id.in_(ids)).group_by(ProtocolVersion.match_id).subquery())
        query = (select(Match.id, ProtocolVersion.snapshot)
                 .join(latest, latest.c.match_id == Match.id)
                 .join(ProtocolVersion, and_(ProtocolVersion.match_id == Match.id, ProtocolVersion.number == latest.c.number)))
    rows = db.execute(query.where(Match.id.in_(ids), Match.status != 'cancelled')).all()
    return {mid: leg for mid, snapshot in rows if (leg := leg_from_snapshot(snapshot))}


def confirmed_match_ids(db, match_ids):
    """Матчи, у которых есть хотя бы одна подтверждённая версия протокола."""
    ids = list({mid for mid in match_ids if mid})
    if not ids: return set()
    return set(db.scalars(select(ProtocolVersion.match_id).where(ProtocolVersion.match_id.in_(ids)).distinct()))
