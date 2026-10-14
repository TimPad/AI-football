from copy import deepcopy
import pytest
from aifootball.ratings.actions import canonical_actions,discipline_cost


def test_confirmed_video_goal_does_not_double_official_goal_or_replace_unknown_author():
    protocol={'events':[{'id':'g1','kind':'goal','player_id':None,'assist_known':False}]}
    reviewed=[{'id':'e1','kind':'goal_candidate','player_id':'person'}]
    before=deepcopy((protocol,reviewed))
    rows=canonical_actions(protocol,reviewed,[{'canonical_event_id':'g1','source_event_id':'e1'}])
    assert len(rows)==1 and rows[0]['kind']=='goal' and rows[0]['player_id'] is None
    assert len(rows[0]['source_refs'])==2 and rows[0]['assist_id'] is None
    assert (protocol,reviewed)==before


def test_own_goal_unknown_assist_and_shootout_remain_distinct():
    rows=canonical_actions({'events':[{'id':'g1','kind':'goal','player_id':'a','own_goal':True,'assist_known':True},
        {'id':'g2','kind':'goal','player_id':'a','assist_id':'b','assist_known':False},
        {'id':'s1','kind':'shootout_attempt','player_id':'a','outcome':'goal'}]},[],[])
    assert len(rows)==2
    assert next(r for r in rows if r['id']=='g1')['counts_as_player_goal'] is False
    assert next(r for r in rows if r['id']=='g2')['assist_id'] is None


def test_penalty_goal_and_successful_attempt_are_one_canonical_shot():
    rows=canonical_actions({'events':[{'id':'p','kind':'penalty_awarded','side':'home'},
        {'id':'a','kind':'penalty_attempt','penalty_id':'p','player_id':'x','outcome':'goal'},
        {'id':'g','kind':'goal','player_id':'x','from_penalty':True,'penalty_id':'p'}]},[],[])
    assert sum(bool(r.get('counts_as_shot')) for r in rows)==1
    goal=next(r for r in rows if r['kind']=='goal')
    assert goal['non_penalty_goal'] is False and len(goal['source_refs'])==2


def test_rejected_and_unlinked_goal_hypotheses_are_not_official_actions():
    rows=canonical_actions({'events':[]},[{'id':'e1','kind':'goal_candidate','player_id':'a'},
        {'id':'e2','kind':'shot','player_id':'a','decision':'rejected'}],[])
    assert rows==[]


@pytest.mark.parametrize('target,source',[
    ({'id':'a','kind':'pass','player_id':'p','start_ms':1000},{'id':'b','kind':'pass','player_id':'p','start_ms':10000}),
    ({'id':'a','kind':'pass','player_id':'p','start_ms':1000},{'id':'b','kind':'pass','player_id':'q','start_ms':1000}),
    ({'id':'a','kind':'pass','player_id':'p','start_ms':1000},{'id':'b','kind':'shot','player_id':'p','start_ms':1000}),
])
def test_distinct_actions_cannot_be_silently_deduplicated(target,source):
    with pytest.raises(ValueError):canonical_actions({'events':[]},[target,source],[{'canonical_event_id':'a','source_event_id':'b'}])


def test_distinct_official_goals_cannot_be_merged():
    with pytest.raises(ValueError):canonical_actions({'events':[{'id':'a','kind':'goal'},{'id':'b','kind':'goal'}]},[],[{'canonical_event_id':'a','source_event_id':'b'}])


def test_incident_max_cost_keeps_first_yellow_as_a_separate_incident():
    events=[{'id':'first','kind':'card','card':'yellow','player_id':'p'},
        {'id':'foul','kind':'foul','player_id':'p'},
        {'id':'dismissal','kind':'card','card':'second_yellow','previous_yellow_id':'first','player_id':'p'}]
    rows=canonical_actions({'events':events},[],[{'kind':'incident','canonical_event_id':'foul','source_event_id':'dismissal'}])
    assert discipline_cost(rows,'p')==7
    with pytest.raises(ValueError):canonical_actions({'events':events},[],[{'kind':'incident','canonical_event_id':'first','source_event_id':'dismissal'}])
