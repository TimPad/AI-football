from datetime import datetime
from typing import Annotated,Literal,Union
from uuid import UUID
from pydantic import Field,model_validator
from aifootball.service.tournaments.schemas import Input
from aifootball.service.db import utcnow
from aifootball.service.errors import DomainError

Side=Literal['home','away']
Millis=Annotated[int,Field(ge=0,le=86400000,strict=True)]


class EventBase(Input):
    id:UUID
    side:Side|None=None
    period:int|None=Field(default=None,ge=1,le=20)
    elapsed_ms:Millis|None=None
    video_ms:Millis|None=None
    notes:str=Field(default='',max_length=4000)
    created_at:datetime=Field(default_factory=utcnow)


class Goal(EventBase):
    kind:Literal['goal']
    player_id:UUID|None=None
    assist_id:UUID|None=None
    assist_known:bool=False
    own_goal:bool=False
    from_penalty:bool=False
    penalty_id:UUID|None=None


class Foul(EventBase):
    kind:Literal['foul']
    player_id:UUID|None=None
    victim_id:UUID|None=None
    accumulated:bool=True
    reason:str=Field(default='',max_length=2000)


class Card(EventBase):
    kind:Literal['card']
    player_id:UUID|None=None
    card:Literal['yellow','second_yellow','red']
    previous_yellow_id:UUID|None=None
    reason:str=Field(default='',max_length=2000)


class PenaltyAwarded(EventBase):
    kind:Literal['penalty_awarded']
    player_id:UUID|None=None
    reason:str=Field(default='',max_length=2000)


class PenaltyAttempt(EventBase):
    kind:Literal['penalty_attempt']
    player_id:UUID|None=None
    penalty_id:UUID
    outcome:Literal['goal','saved','off_target','unknown']


class ShootoutAttempt(EventBase):
    kind:Literal['shootout_attempt']
    player_id:UUID|None=None
    attempt_number:int=Field(ge=1,le=1000)
    outcome:Literal['goal','saved','off_target','unknown']


class Timeout(EventBase):
    kind:Literal['timeout']
    duration_ms:Millis|None=None


class Substitution(EventBase):
    kind:Literal['substitution']
    player_out_id:UUID|None=None
    player_in_id:UUID|None=None


class Stoppage(EventBase):
    kind:Literal['stoppage']
    reason:Literal['injury','technical','other']='other'
    duration_ms:Millis|None=None


class PeriodBoundary(EventBase):
    kind:Literal['period_start','period_end']
    period:int=Field(ge=1,le=20)


Event=Annotated[Union[Goal,Foul,Card,PenaltyAwarded,PenaltyAttempt,ShootoutAttempt,Timeout,
                      Substitution,Stoppage,PeriodBoundary],Field(discriminator='kind')]


def opposite(side): return 'away' if side=='home' else 'home'


def validate_event(event,*,regulation,lineup,events):
    def invalid(message): raise DomainError('event',message,{'event':message})
    if event.video_ms is not None: invalid('Сначала привяжите видео к матчу')
    if isinstance(event,PeriodBoundary):
        if event.side is not None: invalid('Граница периода не относится к команде')
    elif not isinstance(event,Stoppage) and event.side is None:
        invalid('Выберите команду события')
    periods=regulation.periods_s+(regulation.extra.periods_s if regulation.extra.enabled else [])
    if event.period is not None and event.period>len(periods): invalid('Такого периода нет в регламенте')
    if event.elapsed_ms is not None:
        if event.period is None: invalid('Укажите период для игрового времени')
        if event.elapsed_ms>periods[event.period-1]*1000: invalid('Время выходит за пределы периода')
    players={str(p['player_id']):p['side'] for p in lineup}
    for key in ['player_id','assist_id','player_out_id','player_in_id','victim_id']:
        value=getattr(event,key,None)
        if value:
            side=opposite(event.side) if key=='victim_id' else event.side
            if players.get(str(value))!=side: invalid('Участник не входит в состав нужной команды')
    by_id={e.id:e for e in events}
    if len(by_id)!=len(events): invalid('Идентификатор события повторяется')
    if isinstance(event,Goal):
        if event.assist_id and (event.assist_id==event.player_id or not event.assist_known):
            invalid('Укажите другого ассистента и подтвердите сведения об ассисте')
        if event.own_goal and (event.assist_id is not None or not event.assist_known):
            invalid('У автогола не назначается ассист')
        if event.from_penalty:
            award=by_id.get(event.penalty_id)
            attempts=[e for e in events if isinstance(e,PenaltyAttempt) and e.penalty_id==event.penalty_id]
            if not isinstance(award,PenaltyAwarded) or award.side!=event.side or len(attempts)!=1 or attempts[0].outcome!='goal':
                invalid('Свяжите гол с назначением и успешной попыткой пенальти')
            if event.own_goal: invalid('Автогол не является голом с назначенного пенальти')
            if len([e for e in events if isinstance(e,Goal) and e.penalty_id==event.penalty_id])!=1:
                invalid('Пенальти уже связан с другим голом')
        elif event.penalty_id is not None: invalid('Укажите признак гола с пенальти')
    if isinstance(event,PenaltyAttempt):
        award=by_id.get(event.penalty_id)
        if not isinstance(award,PenaltyAwarded) or award.side!=event.side: invalid('Не найдено назначение пенальти этой команды')
        attempts=[e for e in events if isinstance(e,PenaltyAttempt) and e.penalty_id==event.penalty_id]
        goals=[e for e in events if isinstance(e,Goal) and e.penalty_id==event.penalty_id]
        if len(attempts)!=1: invalid('Попытка пенальти повторяется')
        if event.outcome=='goal' and len(goals)!=1: invalid('Успешная попытка должна быть связана с одним голом')
        if event.outcome!='goal' and goals: invalid('Результат попытки не соответствует голу')
        if goals and event.player_id and goals[0].player_id and event.player_id!=goals[0].player_id:
            invalid('Автор гола не соответствует исполнителю пенальти')
    if isinstance(event,ShootoutAttempt):
        if not regulation.shootout.enabled: invalid('Серия пенальти не предусмотрена регламентом')
        if event.period is not None or event.elapsed_ms is not None: invalid('Серия пенальти хранится отдельно от игрового времени')
        if sum(isinstance(e,ShootoutAttempt) and e.side==event.side and e.attempt_number==event.attempt_number for e in events)!=1:
            invalid('Номер попытки этой команды повторяется')
    if isinstance(event,Foul) and event.accumulated and not regulation.fouls.enabled:
        invalid('Накопленные фолы выключены в регламенте')
    if isinstance(event,Card):
        if event.card=='second_yellow':
            prev=by_id.get(event.previous_yellow_id)
            if event.player_id is not None or event.previous_yellow_id is not None:
                if not isinstance(prev,Card) or prev.card!='yellow' or prev.player_id!=event.player_id or prev.side!=event.side:
                    invalid('Выберите предыдущую жёлтую карточку этого игрока')
                ids=[e.id for e in events]
                if ids.index(prev.id)>=ids.index(event.id): invalid('Предыдущая жёлтая должна быть раньше второй')
                if sum(isinstance(e,Card) and e.previous_yellow_id==prev.id for e in events)!=1:
                    invalid('Карточка уже связана с другим удалением')
        elif event.previous_yellow_id is not None: invalid('Связь с жёлтой задаётся только для второй жёлтой')
    if isinstance(event,Substitution) and event.player_out_id and event.player_out_id==event.player_in_id:
        invalid('Игроки замены должны отличаться')
    return event
