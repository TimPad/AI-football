from dataclasses import replace
import json

import pytest

from test_joint_vlm_pilot import environment


SOURCE='a'*64


def fact(value):
    return {'value':value,'origin':'operator_review','reference':'frame:0'}


def passport():
    return {'schema_version':'match-passport-v1','source_sha256':SOURCE,'sport':'futsal',
            'scope':'continuous_excerpt','facts':{'match_status':fact('in_progress'),
            'team_A_color':fact('зелёная'),'team_B_color':fact('оранжевая'),
            'pitch_dimensions_m':None,'regulation':None,'period':None,'goal_orientation':None}}


def document(number=None):
    return {'events':[{'id':'e1','kind':'shot_candidate','start_ms':1000,'end_ms':2000,'team':'A',
                       'track_ids':[1],'evidence_ids':['clip'],'limitations':[],
                       'visual_signals':['ball_visible','kick_contact','ball_toward_goal']}],
            'states':[{'kind':'playing','start_ms':0,'end_ms':12000,'evidence_ids':['clip'],
                       'limitations':[],'visual_signals':['ball_visible','active_ball_play']}],
            'observations':[] if number is None else [{'track_id':1,'video_ms':3000,'number':number,
                       'team':'A','role':'player','evidence_ids':['crop'],'limitations':[]}],
            'phases':[],'highlight_candidates':[],'open_questions':[]}


def test_passport_requires_matching_source_and_explicit_fact_provenance():
    from aifootball.understanding.match_context import validate_passport
    assert validate_passport(passport(),SOURCE)['facts']['period'] is None
    with pytest.raises(ValueError):validate_passport(passport(),'b'*64)
    p=passport();p['facts']['match_status']['origin']='vlm'
    with pytest.raises(ValueError):validate_passport(p,SOURCE)
    p=passport();p['facts']['team_A_color']['reference']=''
    with pytest.raises(ValueError):validate_passport(p,SOURCE)


def test_passport_rejects_invented_fields_invalid_geometry_and_unknown_as_fact():
    from aifootball.understanding.match_context import validate_passport
    p=passport();p['facts']['score']=fact('10:0')
    with pytest.raises(ValueError):validate_passport(p,SOURCE)
    p=passport();p['facts']['pitch_dimensions_m']=fact({'length_m':float('nan'),'width_m':18})
    with pytest.raises(ValueError):validate_passport(p,SOURCE)
    p=passport();p['facts']['match_status']=fact('unknown')
    with pytest.raises(ValueError):validate_passport(p,SOURCE)


def test_history_keeps_all_windows_but_bounded_snapshot_only_recent_events(tmp_path):
    from aifootball.understanding.match_context import MatchChronology
    window,_,_=environment(tmp_path);history=MatchChronology(SOURCE,passport())
    for i in range(20):
        w=replace(window,id=f'w{i}',start_ms=i*12000,end_ms=(i+1)*12000)
        history.add(w,document(),f'request:{i}')
    snapshot=history.snapshot(240000,track_ids=(1,))
    assert len(history.document()['events'])==20
    assert len(snapshot['recent_events'])==8 and len(json.dumps(snapshot,ensure_ascii=False).encode())<=6000
    assert all(e['status']=='unverified' for e in snapshot['recent_events'])
    assert snapshot['confirmed_facts']==passport()['facts']


def test_future_events_and_numbers_never_enter_earlier_snapshot(tmp_path):
    from aifootball.understanding.match_context import MatchChronology
    window,_,_=environment(tmp_path);history=MatchChronology(SOURCE,passport())
    history.add(replace(window,id='future',start_ms=12000,end_ms=24000),document('7'),'future')
    snapshot=history.snapshot(12000,track_ids=(1,))
    assert snapshot['recent_events']==[] and snapshot['number_hints']==[] and snapshot['last_state'] is None


def test_replay_is_idempotent_and_conflicting_receipt_is_rejected(tmp_path):
    from aifootball.understanding.match_context import MatchChronology
    window,_,_=environment(tmp_path);history=MatchChronology(SOURCE,passport())
    history.add(window,document(),'r1');history.add(window,document(),'r1')
    assert len(history.document()['events'])==1
    changed=document();changed['events'][0]['kind']='save_candidate'
    with pytest.raises(ValueError):history.add(window,changed,'r1')


def test_gap_breaks_continuity_and_is_kept_in_memory(tmp_path):
    from aifootball.understanding.match_context import MatchChronology
    window,_,_=environment(tmp_path);history=MatchChronology(SOURCE,passport())
    history.add(window,document(),'r1');history.gap(12000,24000,'unavailable')
    snapshot=history.snapshot(24000,track_ids=(1,))
    assert snapshot['gap_after_last_state'] is True
    assert snapshot['unknown_intervals']==[[12000,24000]]


def test_conflicting_numbers_remain_conflicts_and_only_current_track_hints_are_sent(tmp_path):
    from aifootball.understanding.match_context import MatchChronology
    window,_,_=environment(tmp_path);history=MatchChronology(SOURCE,passport())
    history.add(window,document('7'),'r1')
    history.add(replace(window,id='w2',start_ms=12000,end_ms=24000),document('9'),'r2')
    hint=history.snapshot(24000,track_ids=(1,))['number_hints'][0]
    assert hint['number'] is None and hint['status']=='conflict' and hint['numbers']==['7','9']
    assert history.snapshot(24000,track_ids=(2,))['number_hints']==[]
    assert 'player_id' not in json.dumps(history.document())


def test_unknown_states_are_not_promoted_to_verified_facts(tmp_path):
    from aifootball.understanding.match_context import MatchChronology
    window,_,_=environment(tmp_path);history=MatchChronology(SOURCE,passport());d=document()
    d['states'][0]['kind']='unknown';history.add(window,d,'r1')
    snapshot=history.snapshot(12000)
    assert snapshot['last_state']['kind']=='unknown'
    assert snapshot['confirmed_facts']==passport()['facts']


def test_chronology_rejects_out_of_bounds_times_even_for_synthetic_inputs(tmp_path):
    from aifootball.understanding.match_context import MatchChronology
    window,_,_=environment(tmp_path);history=MatchChronology(SOURCE,passport());d=document()
    d['events'][0]['end_ms']=12001
    with pytest.raises(ValueError):history.add(window,d,'r1')
