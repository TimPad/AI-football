"""Снятие команды после старта этапа: правило половины в группах, техническая победа в сетке, без новых туров в швейцарке."""
from sqlalchemy import select
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.matches.models import Match
from aifootball.service.stages import operations as ops
from aifootball.service.stages.models import Stage, StageWithdrawal
from aifootball.service.stages.schemas import ELIMINATION


def plan(db, tournament, stage, entry_id, rule=None):
    ev = next(e for e in ops.evaluate(db, tournament, 'cabinet') if e.stage.id == stage.id)
    if ev.status == 'completed': raise DomainError('stage_completed', 'Этап уже завершён', status=409)
    if ev.status != 'started': raise DomainError('use_adjust', 'Этап ещё не начался: уберите команду из состава', status=409)
    team = str(entry_id)
    if db.scalar(select(StageWithdrawal).where(StageWithdrawal.stage_id == stage.id, StageWithdrawal.entry_id == entry_id)):
        raise DomainError('already_withdrawn', 'Команда уже снята', status=409)
    own = [f for f in ev.fixtures if not f.bye and team in ev.computed.get(f.id, ())]
    played = [f for f in own if f.id in ev.legs or (f.outcome or {}).get('kind') == 'walkover']
    kind = ev.config.kind
    default = 'elimination' if kind in ELIMINATION else 'swiss' if kind == 'swiss' else ('annul' if 2 * len(played) < len(own) else 'walkover')
    rule = rule or default
    if kind in ('groups', 'round_robin') and rule not in ('annul', 'walkover'): raise DomainError('validation', 'Выберите правило для группы')
    open_ = [f for f in own if f not in played]
    affected = own if rule == 'annul' else open_
    cancel = [f for f in affected if f.match_id and f.id not in ev.legs]
    return ev, team, rule, default, own, played, affected, cancel


def preview(db, tournament, stage, data):
    ev, team, rule, default, own, played, affected, cancel = plan(db, tournament, stage, data.entry_id, data.rule)
    return {'entry_id': team, 'rule': rule, 'default_rule': default, 'played': len(played), 'total': len(own),
            'annulled': len(affected) if rule == 'annul' else 0, 'walkovers': len(affected) if rule == 'walkover' else 0,
            'cancelled_matches': len(cancel)}


def withdraw(db, actor, tournament, stage, data):
    stage = get_entity(db, Stage, stage.id, lock=True)
    if data.expected_revision is None: raise DomainError('validation', 'Обновите страницу и повторите')
    if stage.revision != data.expected_revision: raise ops.stage_conflict(stage)
    ev, team, rule, _, own, played, affected, cancel = plan(db, tournament, stage, data.entry_id, data.rule)
    score = ev.config.walkover_score
    for f in affected:
        if rule == 'annul': f.outcome = {'kind': 'annulled'}
        elif rule in ('walkover', 'swiss'):
            home, _ = ev.computed[f.id]
            f.outcome = {'kind': 'walkover', 'winner': 'away' if home == team else 'home', 'score': score}
    for f in cancel:
        match = get_entity(db, Match, f.match_id, lock=True); match.status = 'cancelled'; match.revision += 1
    db.add(StageWithdrawal(stage_id=stage.id, entry_id=data.entry_id, rule=rule, played=len(played), total=len(own), actor_id=actor.id))
    stage.revision += 1
    db.flush()
    return ops.standings(db, tournament, 'cabinet')
