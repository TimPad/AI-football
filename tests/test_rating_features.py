from dataclasses import replace
from uuid import uuid4
import pytest
from aifootball.ratings.schema import MatchPerformance,MetricFact
from aifootball.ratings.actions import canonical_actions
from aifootball.ratings.features import build_features,aggregate_facts,combine_rate
from aifootball.ratings.registry import REGISTRY

PID=str(uuid4());OTHER=str(uuid4());MID=str(uuid4());TID=str(uuid4())
CATEGORIES=('goals','assists','shots','passes','carries','duels','recoveries','shot_blocks','turnovers','fouls','cards','errors','saves','distribution')


def performance(**changes):
    provenance={'side':'home','clock_basis':'game','analysis_scope':'full_match','source_kind':'manual_verified',
        'categories':{c:'complete' for c in CATEGORIES},'role_intervals':[[0,600000]],'eligible_intervals':[[0,600000]],
        'single_role':True,'presence_verified':True,'pitch':{'length_m':40,'width_m':20},
        'possession_s':300,'without_possession_s':200}
    provenance.update(changes.pop('provenance',{}))
    return replace(
        MatchPerformance(TID,MID,PID,'ala','reviewed_effective',600,600,1,{},provenance),**changes)


def action(kind,**changes):
    return {'id':str(uuid4()),'kind':kind,'player_id':PID,'side':'home','verified':True,'clock_basis':'game','start_ms':1000,**changes}


def build(row=None,actions=None,profile='per10'):
    return build_features(row or performance(),actions or [],profile_id=profile)


def test_tournament_rate_is_ratio_of_sums():
    result=combine_rate([MetricFact(2,2,600,'count/10min','complete',None),MetricFact(.5,1,1200,'count/10min','complete',None)])
    assert result.value==1 and result.numerator==3 and result.denominator==1800


def test_complete_zero_unknown_and_zero_opportunities_are_distinct():
    facts=build();assert facts['recoveries_rate10'].value==0
    assert facts['shots_on_target_pct'].value is None and facts['shots_on_target_pct'].denominator==0
    assert facts['shots_on_target_pct'].reason=='no_opportunities'
    row=performance(provenance={'categories':{'recoveries':'partial'}})
    facts=build(row,[action('recovery')]);assert facts['recoveries_count'].value is None
    assert facts['recoveries_known_count'].value==1 and facts['recoveries_rate10'].value is None


@pytest.mark.parametrize('scope',['full_match','highlights','continuous_excerpt','unknown'])
def test_video_scope_or_complete_processing_alone_never_proves_categories(scope):
    row=performance(provenance={'analysis_scope':scope,'source_kind':'reviewed_video','categories':{}})
    assert build(row,[action('recovery')])['recoveries_rate10'].value is None
    row=replace(row,provenance={**row.provenance,'source_kind':'manual_verified','analysis_scope':'full_match','categories':{'recoveries':'complete'},'additional_video_scope':scope})
    assert build(row,[action('recovery')])['recoveries_rate10'].value==1


def test_possession_profiles_use_known_matching_denominators():
    events=[action('recovery')]
    assert build(actions=events,profile='per10-possession')['recoveries_rate10'].value==3
    row=performance(provenance={'without_possession_s':None})
    assert build(row,events,'per10-possession')['recoveries_rate10'].denominator is None
    row=performance(provenance={'without_possession_s':0})
    assert build(row,[], 'per10-possession')['recoveries_rate10'].reason=='no_opportunities'
    with pytest.raises(ValueError):build(profile='per90')


def test_foreign_actions_and_unassigned_role_times_are_not_spread_proportionally():
    events=[action('recovery',player_id=OTHER),action('recovery',start_ms=30000),action('recovery',start_ms=90000),action('recovery',start_ms=None)]
    row=performance(eligible_play_s=60,provenance={'role_intervals':[[0,60000]],'eligible_intervals':[[0,60000]],'single_role':False})
    facts=build(row,events)
    assert facts['recoveries_known_count'].value==1
    assert facts['recoveries_rate10'].value is None  # unallocated actor action makes role total unknown
    facts=build(row,events[:-1]);assert facts['recoveries_rate10'].value==10


def test_protocol_unknown_author_assist_own_goal_and_shootout():
    events=[action('goal',player_id=None,assist_known=False),action('goal',own_goal=True,assist_known=True),
        action('shootout_attempt',outcome='goal')]
    actions=canonical_actions({'events':events},[],[])
    facts=build(actions=actions)
    assert facts['npg_rate10'].value is None and facts['assists_rate10'].value is None
    assert facts['npg_known_count'].value==0 and facts['assists_known_count'].value==0


def test_key_pass_chain_breaks_at_intervening_pass_unknown_touch_or_opponent_control():
    pid=PID;pos=str(uuid4())
    first=action('pass',success=True,possession_id=pos,start_ms=1000)
    shot=action('shot',player_id=OTHER,counts_as_shot=True,on_target=True,possession_id=pos,start_ms=3000)
    assert build(actions=[first,shot])['key_pass_rate10'].value==1
    for middle in [action('pass',player_id=OTHER,success=True,possession_id=pos,start_ms=2000),
        action('turnover',start_ms=2000,possession_id=pos),
        action('recovery',side='away',player_id=OTHER,start_ms=2000,possession_id=pos)]:
        assert build(actions=[first,middle,shot])['key_pass_rate10'].value==0
    assert build(actions=[{**first,'chain_complete':False},shot])['key_pass_rate10'].value is None


def test_progression_and_dangerous_turnover_use_real_length_and_verified_control():
    row=performance(provenance={'pitch':{'length_m':44,'width_m':20}})
    events=[action('pass',success=True,start_xy=[10.5,3],end_xy=[11,3],attacking_direction='right'),
        action('turnover',start_xy=[10.5,3],attacking_direction='right',opponent_id=OTHER)]
    facts=build(row,events);assert facts['progression_rate10'].value==1 and facts['dangerous_turnover_rate10'].value==1
    missing=build(row,[{**events[0],'attacking_direction':'unknown'}]);assert missing['progression_rate10'].value is None


def test_unresolved_attempts_are_not_zero_opportunities():
    facts=build(actions=[action('pass',success=None),action('duel',success=None)])
    assert facts['pass_completion_pct'].denominator==0 and facts['pass_completion_pct'].reason=='unresolved_attempts'
    assert facts['pass_completion_unresolved_count'].value==1


def test_goalkeeper_only_faces_goals_during_verified_goalkeeper_stints():
    row=performance(role='goalkeeper',eligible_play_s=60,provenance={'role_intervals':[[0,60000]],'eligible_intervals':[[0,60000]],'single_role':False})
    events=[action('save',success=True),action('goal',player_id=OTHER,side='away',own_goal=False),
        action('goal',player_id=OTHER,side='away',start_ms=90000),action('goal',player_id=OTHER,side='away',own_goal=True)]
    assert build(row,events)['save_pct'].value==50
    assert build(replace(row,provenance={**row.provenance,'presence_verified':False}),events)['save_pct'].value is None


def test_aggregate_compatible_ratios_maxima_and_incompatible_geometry():
    rows=[performance(facts={'pass_completion_pct':MetricFact(50,1,2,'percent','complete',None),
        'vmax_ms':MetricFact(4,4,None,'m/s','complete',None),'npg_rate10':MetricFact(2,2,600,'count/10min','complete',None)}),
        performance(match_id=str(uuid4()),facts={'pass_completion_pct':MetricFact(100,8,8,'percent','complete',None),
        'vmax_ms':MetricFact(6,6,None,'m/s','complete',None),'npg_rate10':MetricFact(.5,1,1200,'count/10min','complete',None)})]
    result=aggregate_facts(rows);assert result['pass_completion_pct'].value==90 and result['vmax_ms'].value==6
    assert result['npg_rate10'].value==1
    with pytest.raises(ValueError):aggregate_facts([rows[0],replace(rows[1],time_basis='running_clock')])
    assert all(REGISTRY[key]['time_bases'] for key in ('save_pct','progression_rate10'))


def test_assist_without_role_time_and_unknown_side_author_do_not_become_zero():
    row=performance(provenance={'single_role':False})
    goal=action('goal',player_id=OTHER,assist_id=PID,assist_known=True,start_ms=None)
    assert build(row,[goal])['assists_rate10'].value is None
    unknown=action('goal',side=None,player_id=None,non_penalty_goal=True)
    assert build(actions=[unknown])['npg_rate10'].value is None


def test_unresolved_pass_before_shot_does_not_prove_zero_key_passes():
    pos=str(uuid4())
    events=[action('pass',success=None,possession_id=pos),action('shot',start_ms=2000,possession_id=pos,on_target=True)]
    assert build(actions=events)['key_pass_rate10'].value is None


def test_maps_stay_separate_even_when_scalar_cells_have_same_unit():
    one=performance(facts={'heatmap':MetricFact(4,4,None,'heatmap-seconds','complete',None)})
    two=performance(match_id=str(uuid4()),provenance={'pitch':{'length_m':44,'width_m':18}},
        facts={'heatmap':MetricFact(5,5,None,'heatmap-seconds','complete',None)})
    assert aggregate_facts([one,two])['heatmap'].value is None


def test_unattributed_actions_do_not_prove_individual_zero_for_affected_team():
    event=action('recovery',player_id=None)
    assert build(actions=[event])['recoveries_rate10'].value is None
    assert build(actions=[{**event,'side':'away'}])['recoveries_rate10'].value==0
