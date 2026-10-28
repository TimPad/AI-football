"""Правка состава этапа до старта: новая версия жеребьёвки с ручной расстановкой."""
from aifootball.service.errors import DomainError
from aifootball.service.stages.schemas import DrawConfirm, DrawInput, ELIMINATION
from aifootball.service.stages import operations as ops


def adjusted(stage, draw, data):
    """(участники, расстановка) после правки."""
    entry = str(data.entry_id); config = ops.config_of(stage)
    if config.source.get('previous'):
        raise DomainError('validation', 'Состав этого этапа берётся из предыдущего: правьте его там')
    participants = [str(p) for p in (draw.participants or draw.seeding)]
    placement = [list(g) for g in draw.placement] if config.kind == 'groups' else list(draw.placement)
    present = entry in participants
    if data.op == 'remove':
        if not present: raise DomainError('validation', 'Этой команды нет в этапе')
        participants.remove(entry)
        if config.kind == 'groups':
            placement = [[t for t in g if t != entry] for g in placement]
            if any(len(g) < 2 for g in placement): raise DomainError('validation', 'В группе должно остаться минимум две команды')
        elif config.kind in ELIMINATION:
            placement = [None if s and s.get('entry') == entry else s for s in placement]
        else:
            placement = [t for t in placement if t != entry]
    elif data.op == 'add':
        if present: raise DomainError('validation', 'Команда уже в этапе')
        participants.append(entry)
        if config.kind == 'groups':
            target = (data.group_no or min(range(1, len(placement) + 1), key=lambda g: (len(placement[g - 1]), g))) - 1
            placement[target].append(entry)
        elif config.kind in ELIMINATION:
            if None not in placement: raise DomainError('no_free_slot', 'Свободных мест нет. Проведите жеребьёвку заново', status=409)
            placement[placement.index(None)] = {'entry': entry}
        else:
            placement.append(entry)
    else:
        if config.kind != 'groups' or not data.group_no or not present:
            raise DomainError('validation', 'Перенести можно команду этапа в другую группу')
        placement = [[t for t in g if t != entry] for g in placement]; placement[data.group_no - 1].append(entry)
        if any(len(g) < 2 for g in placement): raise DomainError('validation', 'В группе должно остаться минимум две команды')
    return participants, placement


def preview_adjust(db, tournament, stage, data):
    draw = ops.current_draw(db, stage.id)
    if draw is None: raise DomainError('validation', 'Сначала проведите жеребьёвку')
    participants, placement = adjusted(stage, draw, data)
    return ops.preview_draw(db, tournament, stage, DrawInput(method='manual', seed=draw.seed, seeding=participants,
                                                             participants=participants, placement=placement))


def apply_adjust(db, actor, tournament, stage, data):
    draw = ops.current_draw(db, stage.id)
    if draw is None: raise DomainError('validation', 'Сначала проведите жеребьёвку')
    participants, placement = adjusted(stage, draw, data)
    return ops.confirm_draw(db, actor, tournament, stage, DrawConfirm(method='manual', seed=draw.seed, seeding=participants,
        participants=participants, placement=placement, expected_revision=data.expected_revision, request_id=data.request_id))
