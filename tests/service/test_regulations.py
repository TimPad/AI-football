import pytest
from pydantic import ValidationError


def test_duration_and_mixed_window(regulation_data):
    from aifootball.service.tournaments.schemas import Regulation
    r=Regulation.model_validate(regulation_data)
    assert r.total_s==2400
    with pytest.raises(ValidationError):
        Regulation.model_validate({**regulation_data,'periods_s':[0,1200]})
    with pytest.raises(ValidationError):
        Regulation.model_validate({**regulation_data,'clock_mode':'mixed','mixed_stop_last_s':1201})


@pytest.mark.parametrize('change',[{'break_s':[]},{'match_roster_limit':4},
    {'pitch_width_m':0},{'periods_s':[-1,1200]},{'periods_s':[1]*11},
    {'tournament_roster_limit':4},{'extra':{'enabled':True,'periods_s':[300],
         'clock_mode':'mixed','mixed_stop_last_s':400}}])
def test_incoherent_rules_rejected(regulation_data, change):
    from aifootball.service.tournaments.schemas import Regulation
    with pytest.raises(ValidationError):
        Regulation.model_validate({**regulation_data,**change})
