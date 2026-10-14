from copy import deepcopy
import pytest

HOME='11111111-1111-4111-8111-111111111111'
AWAY='22222222-2222-4222-8222-222222222222'
ROSTER=[{'player_id':HOME,'side':'home','shirt_number':'7'},{'player_id':AWAY,'side':'away','shirt_number':'7'}]


def observation(**changes):
    return {'track_id':1,'team':'A','number':'7','role':'player','video_ms':1000,
            'evidence_ids':['f1'],'visible_features':[],'limitations':[],**changes}


def resolve(items,**kwargs):
    from aifootball.understanding.identity import resolve_identity
    return resolve_identity(items,kwargs.pop('rosters',ROSTER),side_map=kwargs.pop('side_map',{'A':'home','B':'away'}),**kwargs)


def test_same_number_requires_confirmed_side_map():
    assert resolve([observation()],side_map=None)[0]['player_id'] is None
    assert resolve([observation()])[0]['player_id']==HOME
    assert resolve([observation()],side_map={'A':'away','B':'home'})[0]['player_id']==AWAY


def test_conflicting_numbers_do_not_use_majority_vote():
    result=resolve([observation(),observation(),observation(number='17')])[0]
    assert result['player_id'] is None and result['status']=='conflict'


def test_duplicate_roster_number_does_not_choose_first_player():
    roster=[*ROSTER,{'player_id':AWAY,'side':'home','shirt_number':'7'}]
    result=resolve([observation()],rosters=roster)[0]
    assert result['player_id'] is None and result['status']=='conflict'


@pytest.mark.parametrize('role',['referee','unknown'])
def test_non_player_has_no_uuid_suggestion(role):
    assert resolve([observation(role=role)])[0]['player_id'] is None


def test_simultaneous_fragments_cannot_both_suggest_one_player():
    result=resolve([observation(),observation(track_id=2)],track_intervals={1:[[0,2]],2:[[1,3]]})
    assert all(item['status']=='conflict' and item['player_id'] is None for item in result)
