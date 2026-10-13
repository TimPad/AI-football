from aifootball.service.errors import DomainError


def period_rules(regulation,period):
    if period<=len(regulation.periods_s):
        return regulation.periods_s[period-1],regulation.clock_mode,regulation.mixed_stop_last_s
    extra=period-len(regulation.periods_s)-1
    if not regulation.extra.enabled or not 0<=extra<len(regulation.extra.periods_s):
        raise DomainError('clock','Такого периода нет в регламенте')
    return regulation.extra.periods_s[extra],regulation.extra.clock_mode,regulation.extra.mixed_stop_last_s


def clock_elapsed(state,*,now_ms,regulation):
    duration,_,_=period_rules(regulation,state.period)
    delta=max(0,now_ms-state.anchor_utc_ms) if state.phase=='running' and state.anchor_utc_ms is not None else 0
    return min(duration*1000,state.elapsed_ms+delta)


def transition_clock(state,action,*,now_ms,regulation,elapsed_ms=None):
    s=state.model_copy(deep=True)
    duration,mode,window=period_rules(regulation,s.period)
    current=clock_elapsed(s,now_ms=now_ms,regulation=regulation)
    def invalid(message): raise DomainError('clock',message)
    if s.phase=='running' and s.anchor_utc_ms is not None and now_ms<s.anchor_utc_ms:
        s.warning='Время сервера изменилось; проверьте ручные часы'
    else: s.warning=None
    if action=='start':
        if s.phase=='ended':
            s.period+=1; period_rules(regulation,s.period)
        elif s.phase!='not_started': invalid('Для остановленных часов используйте возобновление')
        s.elapsed_ms=0; s.phase='running'; s.anchor_utc_ms=now_ms; s.break_started_utc_ms=None
    elif action=='pause':
        if s.phase!='running': invalid('Часы не запущены')
        if mode=='running': invalid('Непрерывные часы не останавливаются при паузах игры')
        if mode=='mixed' and current<(duration-window)*1000: invalid('Чистое время этого тайма ещё не началось')
        s.elapsed_ms=current; s.phase='paused'; s.anchor_utc_ms=None
    elif action=='resume':
        if s.phase!='paused': invalid('Часы не остановлены')
        s.phase='running'; s.anchor_utc_ms=now_ms
    elif action=='set':
        if elapsed_ms is None or not 0<=elapsed_ms<=duration*1000: invalid('Время выходит за длительность тайма')
        s.elapsed_ms=elapsed_ms; s.anchor_utc_ms=now_ms if s.phase=='running' else None
    elif action=='end_period':
        if s.phase not in ['running','paused']: invalid('Тайм не начат или уже завершён')
        s.elapsed_ms=current; s.phase='ended'; s.anchor_utc_ms=None; s.break_started_utc_ms=now_ms
    else: invalid('Неизвестная команда секундомера')
    return s
