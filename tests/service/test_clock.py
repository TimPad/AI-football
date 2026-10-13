import pytest


def test_clean_clock_excludes_pauses(regulation_data):
    from aifootball.service.protocol.clock import transition_clock,clock_elapsed
    from aifootball.service.protocol.schemas import ClockState
    from aifootball.service.tournaments.schemas import Regulation
    r=Regulation(**regulation_data)
    s=transition_clock(ClockState(),'start',now_ms=1000,regulation=r)
    s=transition_clock(s,'pause',now_ms=11000,regulation=r)
    assert clock_elapsed(s,now_ms=21000,regulation=r)==10000
    s=transition_clock(s,'resume',now_ms=21000,regulation=r)
    assert clock_elapsed(s,now_ms=26000,regulation=r)==15000
    assert r.periods_s[0]*1000-clock_elapsed(s,now_ms=26000,regulation=r)==1185000


def test_running_mixed_and_extra_modes(regulation_data):
    from aifootball.service.protocol.clock import transition_clock
    from aifootball.service.protocol.schemas import ClockState
    from aifootball.service.tournaments.schemas import Regulation
    from aifootball.service.errors import DomainError
    running=Regulation(**{**regulation_data,'clock_mode':'running'})
    s=transition_clock(ClockState(),'start',now_ms=0,regulation=running)
    with pytest.raises(DomainError): transition_clock(s,'pause',now_ms=1000,regulation=running)
    mixed=Regulation(**{**regulation_data,'clock_mode':'mixed','mixed_stop_last_s':120})
    s=transition_clock(ClockState(),'start',now_ms=0,regulation=mixed)
    with pytest.raises(DomainError): transition_clock(s,'pause',now_ms=1079999,regulation=mixed)
    paused=transition_clock(s,'pause',now_ms=1080000,regulation=mixed)
    assert paused.phase=='paused'
    extra=Regulation(**{**regulation_data,'clock_mode':'running','extra':{'enabled':True,'periods_s':[300], 'clock_mode':'clean'}})
    s=ClockState(period=2,phase='ended',elapsed_ms=1200000)
    s=transition_clock(s,'start',now_ms=1,regulation=extra)
    assert s.period==3
    assert transition_clock(s,'pause',now_ms=1001,regulation=extra).phase=='paused'


def test_clock_boundaries_corrections_and_backward_time(regulation_data):
    from aifootball.service.protocol.clock import transition_clock,clock_elapsed
    from aifootball.service.protocol.schemas import ClockState
    from aifootball.service.tournaments.schemas import Regulation
    from aifootball.service.errors import DomainError
    r=Regulation(**regulation_data)
    s=transition_clock(ClockState(),'start',now_ms=1000,regulation=r)
    assert clock_elapsed(s,now_ms=500,regulation=r)==0
    assert clock_elapsed(s,now_ms=2000000,regulation=r)==1200000
    assert s.phase=='running'
    with pytest.raises(DomainError): transition_clock(s,'set',now_ms=1001,regulation=r,elapsed_ms=1200001)
    s=transition_clock(s,'set',now_ms=1002,regulation=r,elapsed_ms=5000)
    assert clock_elapsed(s,now_ms=2002,regulation=r)==6000
