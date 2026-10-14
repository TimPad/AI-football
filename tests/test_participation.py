from copy import deepcopy
from uuid import uuid4
import pytest
from aifootball.ratings.validate import exposure_by_role,validate_participation
from aifootball.ratings.schema import MetricFact


def player(**changes):
    return {'player_id':str(uuid4()),'presence':[[0,60000],[90000,150000]],'completeness':'complete',
        'roles':[{'role':'ala','intervals':[[0,60000],[90000,150000]]}],**changes}


def test_repeated_stints_intersect_playing_time_once():
    result=exposure_by_role(player(),[[0,30000],[100000,150000]],[])
    assert result['ala']['effective_play_s']==80
    assert result['ala']['on_pitch_s']==120
    assert result['ala']['possession_s']==0


def test_partial_presence_keeps_known_time_but_does_not_invent_total_minutes():
    result=exposure_by_role(player(completeness='partial'),None,None)['ala']
    assert result['on_pitch_s'] is None and result['known_on_pitch_s']==120
    assert result['effective_play_s'] is None


def test_unknown_role_is_not_automatically_universal():
    value=player(roles=[{'role':'ala','intervals':[[0,30000]]}])
    result=exposure_by_role(value,None,None)
    assert result['unknown']['on_pitch_s']==90
    assert 'universal' not in result


def test_verified_official_clean_game_axis_does_not_subtract_stoppages_twice():
    result=exposure_by_role(player(time_basis='official_clean'),None,None)['ala']
    assert result['effective_play_s']==120 and result['eligible_play_s']==120


@pytest.mark.parametrize('value',[float('nan'),float('inf'),True,-1])
def test_metric_fact_rejects_non_finite_bool_and_negative_counts(value):
    with pytest.raises(ValueError):MetricFact(value,value,10,'count','complete',None)


def test_roster_capacity_and_manpower_are_checked_on_half_open_intervals():
    people=[player(presence=[[0,10000]],roles=[{'role':'ala','intervals':[[0,10000]]}]) for _ in range(6)]
    roster=[{'player_id':p['player_id'],'side':'home'} for p in people]
    doc={'duration_ms':20000,'players':people,'initial_five':{'home':[],'away':[]},'play_intervals':None,
         'possession_intervals':{'home':None,'away':None},'manpower':[]}
    with pytest.raises(ValueError,match='capacity'):validate_participation(doc,roster,players_on_pitch=5)
    doc['players']=people[:5]
    validate_participation(doc,roster,players_on_pitch=5)
    doc['manpower']=[{'side':'home','start_ms':0,'end_ms':10000,'max_players':4,'powerplay':False,'reason':'Удаление'}]
    with pytest.raises(ValueError,match='capacity'):validate_participation(doc,roster,players_on_pitch=5)
    doc['manpower'][0].update(max_players=5,powerplay=True)
    validate_participation(doc,roster,players_on_pitch=5)


def test_role_overlap_and_roles_outside_presence_are_rejected():
    p=player();doc={'duration_ms':180000,'players':[p],'initial_five':{'home':[],'away':[]},
        'play_intervals':None,'possession_intervals':{'home':None,'away':None},'manpower':[]}
    roster=[{'player_id':p['player_id'],'side':'home'}]
    p['roles'].append({'role':'pivot','intervals':[[30000,40000]]})
    with pytest.raises(ValueError,match='role'):validate_participation(doc,roster,players_on_pitch=5)
    p['roles']=[{'role':'ala','intervals':[[60000,90000]]}]
    with pytest.raises(ValueError,match='presence'):validate_participation(doc,roster,players_on_pitch=5)
