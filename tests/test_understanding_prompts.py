import json
from understanding_fixtures import make_frame


def window(tmp_path):
    from aifootball.understanding.types import Window
    return Window('w1',0,2000,(make_frame(tmp_path),),None,(1,),'frames')


def test_match_prompt_contract_covers_futsal_groups_and_only_measured_values(tmp_path):
    from aifootball.understanding.prompts import match_prompt
    payload=json.loads(match_prompt(window(tmp_path),measured={'distance_m':10,'name':'secret-player','api_key':'secret-key'}))
    assert payload['task']=='match'
    assert payload['response']['time_basis']=='window'
    for kind in ['goal_candidate','save_candidate','substitution_candidate','keeper_out_candidate','pressing_candidate','compact_block_candidate','kick_in']:
        assert kind in payload['enums']['event']
    assert payload['window']['track_ids']==[1]
    assert 'secret-player' not in json.dumps(payload) and 'secret-key' not in json.dumps(payload)
    assert payload['scope']=='unknown'


def test_identity_prompt_carries_evidence_and_does_not_request_player_names(tmp_path):
    from aifootball.understanding.prompts import identity_prompt
    payload=json.loads(identity_prompt(window(tmp_path)))
    assert payload['task']=='identity'
    assert payload['window']['evidence_ids']==['f25']
    assert payload['response']['observations']==[]
    assert 'player_id' not in payload['response']
    assert payload['enums']['role']==['player','goalkeeper','referee','unknown']


def test_scene_prompt_grounds_track_ids_in_normalized_frame_boxes(tmp_path):
    from aifootball.understanding.prompts import match_prompt
    payload=json.loads(match_prompt(window(tmp_path),measured={
        'track_boxes':{'f25':[[1,.1,.2,.3,.8],[99,.1,.1,.2,.2]]},
        'track_teams':{1:'A',99:'B'}}))
    assert payload['window']['track_boxes']=={'f25':[[1,.1,.2,.3,.8]]}
    assert payload['window']['track_teams']=={'1':'A'}
