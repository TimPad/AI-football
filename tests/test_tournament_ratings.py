from copy import deepcopy
import json
from pathlib import Path
import pytest
from aifootball.ratings.aggregate import tournament_rating,rank_players

POLICY=json.loads(Path('configs/ratings/role-profile-v1.json').read_text())


def match(mid='m1',**changes):return {'match_id':mid,'player_id':'p1','role':'ala','score':80,'eligible_play_minutes':10,'played_minutes':10,
    'appeared':True,'result_type':'played','status':'completed','model_version':'v1','reference_version':'r1','profile_id':'per10','time_basis':'reviewed_effective',**changes}


def test_small_sample_is_pulled_to_baseline():
    assert tournament_rating([match()])['score']==57.5
    five=[match(f'm{i}') for i in range(5)]
    result=tournament_rating(five);assert result['score']==68.75 and result['baseline_influence']==3/8
    assert tournament_rating([])['score'] is None


def test_short_appearance_unknown_total_and_unrated_match_are_explicit():
    assert tournament_rating([match(eligible_play_minutes=1,played_minutes=1)])['score'] is None
    rows=[match(f'm{i}') for i in range(3)]+[match('m4',score=None,played_minutes=None,eligible_play_minutes=None)]
    result=tournament_rating(rows)
    assert result['match_count']==4 and result['rated_match_count']==3 and result['coverage'] is None
    ranks=rank_players(rows,role=None,policy=POLICY)
    assert ranks[0]['qualification']=='unknown' and ranks[0]['rank'] is None
    rows[-1]=match('m4',score=None)
    result=rank_players(rows,role=None,policy=POLICY)[0]
    assert result['coverage']==.75 and result['qualification']=='preliminary' and result['score'] is not None


def test_technical_cancelled_and_bench_are_not_appearances():
    rows=[match('tech',result_type='technical'),match('cancelled',status='cancelled'),match('bench',appeared=False)]
    result=tournament_rating(rows);assert result['score'] is None and result['match_count']==0


def test_multiple_roles_one_appearance_one_capped_match_weight():
    rows=[match(role='fixo',score=20,eligible_play_minutes=5,played_minutes=5),match(role='ala',score=80,eligible_play_minutes=15,played_minutes=15)]
    result=tournament_rating(rows)
    assert result['match_count']==1 and result['rated_match_count']==1 and result['weight_sum']==1
    assert result['score']==pytest.approx((65+150)/4)
    result=rank_players(rows,role='fixo',policy=POLICY)[0]
    assert result['eligible_play_minutes']==5 and result['score']==pytest.approx((.5*20+150)/3.5)


def test_missing_role_part_is_not_proportionally_filled():
    rows=[match(role='ala',eligible_play_minutes=5,played_minutes=5),match(role='unknown',score=None,eligible_play_minutes=5,played_minutes=5)]
    result=tournament_rating(rows);assert result['score'] is None and result['rated_match_count']==0


def test_equal_unrounded_scores_share_rank_uuid_only_stabilizes_display():
    rows=[match(f'm{i}',player_id=pid) for pid in ('p2','p1') for i in range(3)]
    result=rank_players(rows,role=None,policy=POLICY)
    assert [r['player_id'] for r in result]==['p1','p2'] and [r['rank'] for r in result]==[1,1]
    assert all(r['qualification']=='qualified' for r in result)
    altered=[match(f'z{i}',player_id='p3',score=79.9999) for i in range(3)]
    result=rank_players([*rows,*altered],role=None,policy=POLICY)
    assert result[-1]['rank']==3


def test_mixed_editions_duplicate_roles_and_two_versions_are_rejected():
    with pytest.raises(ValueError):tournament_rating([match(),match('m2',reference_version='different')])
    with pytest.raises(ValueError):tournament_rating([match(),match()])
    with pytest.raises(ValueError):tournament_rating([match(role='ala',selected_source='a'),match(role='fixo',selected_source='b')])
    with pytest.raises(ValueError):tournament_rating([match(),match('m2',player_id='p2')])


def test_no_rated_matches_is_null_not_baseline_and_matches_are_not_mutated():
    rows=[match(score=None)];before=deepcopy(rows)
    result=tournament_rating(rows);assert result['score'] is None and result['weight_sum']==0
    assert rows==before


def test_qualification_uses_minutes_and_roles_independently():
    rows=[]
    for i in range(3):
        rows.extend([match(f'm{i}',role='ala',eligible_play_minutes=9,played_minutes=9),match(f'm{i}',role='fixo',eligible_play_minutes=1,played_minutes=1)])
    assert rank_players(rows,role=None,policy=POLICY)[0]['qualification']=='qualified'
    assert rank_players(rows,role='ala',policy=POLICY)[0]['qualification']=='qualified'
    assert rank_players(rows,role='fixo',policy=POLICY)[0]['qualification']=='preliminary'
