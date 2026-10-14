from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timezone
import json
from pathlib import Path
from uuid import uuid4
import pytest
from aifootball.ratings.schema import MatchPerformance,MetricFact
from aifootball.ratings.registry import REGISTRY
from aifootball.ratings.reference import build_reference
from aifootball.ratings.scoring import percentile,score_match,validate_policy


@pytest.fixture
def policy():return json.loads(Path('configs/ratings/role-profile-v1.json').read_text())


def complete_features(value=1):
    return {key:MetricFact(value,1,600,'count/10min','complete',None) if spec['unit']=='count/10min' else MetricFact(50,1,2,'percent','complete',None) for key,spec in REGISTRY.items()}


def cohort(policy,*,role='fixo',count=20,players=5):
    tid=str(uuid4());pids=[str(uuid4()) for _ in range(players)]
    return [MatchPerformance(tid,str(uuid4()),pids[i%players],role,'reviewed_effective',600,600,1,complete_features(),
        {'profile_id':'per10','level':'amateur','played_at':'2026-10-01T12:00:00Z','source_version':str(uuid4())}) for i in range(count)]


def reference(policy,**kwargs):return build_reference(cohort(policy,**kwargs),policy=policy,cutoff='2026-10-14T00:00:00Z')


def test_tied_metrics_and_inverse_get_neutral_percentile():
    assert percentile(0,[0,0,0])==50
    assert percentile(2,[1,2,2,3])==50
    assert percentile(3,[1,2,3],lower_is_better=True)==pytest.approx(100/6)


def test_complete_profile_is_explained_and_physical_workload_has_zero_weight(policy):
    features=complete_features();ref=reference(policy)
    result=score_match(features,role='fixo',policy=policy,reference=ref)
    assert result['score']==50 and result['display_rating']==5.5
    assert sum(result['contributions'].values())==result['score']
    assert result['model_version']=='role-profile-v1' and result['reference_version']==ref['reference_version']
    features['distance_m']=MetricFact(99999,99999,None,'m','complete',None)
    assert score_match(features,role='fixo',policy=policy,reference=ref)==result


def test_incomplete_defence_cannot_be_hidden_by_goals(policy):
    features=complete_features(100);features['recoveries_rate10']=MetricFact(None,None,None,'count/10min','unknown','No annotation')
    result=score_match(features,role='fixo',policy=policy,reference=reference(policy))
    assert result['score'] is None and result['reasons']
    assert result['components']['Defence'] is None


def test_zero_opportunities_are_neutral_unknown_are_missing(policy):
    features=complete_features();features['shots_on_target_pct']=MetricFact(None,0,0,'percent','complete','no_opportunities')
    result=score_match(features,role='pivot',policy=policy,reference=reference(policy,role='pivot'))
    assert result['feature_scores']['shots_on_target_pct']==50
    features['shots_on_target_pct']=MetricFact(None,None,None,'percent','unknown','Unknown shots')
    assert score_match(features,role='pivot',policy=policy,reference=reference(policy,role='pivot'))['score'] is None


def test_gk_needs_stopping_but_not_outfield_finishing(policy):
    ref=reference(policy,role='goalkeeper');features=complete_features()
    del features['npg_rate10'];del features['recoveries_rate10']
    assert score_match(features,role='goalkeeper',policy=policy,reference=ref)['score']==50
    features['save_pct']=MetricFact(None,None,None,'percent','unknown','Unknown faced shots')
    assert score_match(features,role='goalkeeper',policy=policy,reference=ref)['score'] is None


@pytest.mark.parametrize('players,count',[(4,20),(5,19)])
def test_small_cohort_has_no_score(policy,players,count):
    result=score_match(complete_features(),role='fixo',policy=policy,reference=reference(policy,players=players,count=count))
    assert result['score'] is None and 'insufficient_reference' in result['reasons']


def test_reference_is_immutable_content_addressed_cutoff_and_compatible(policy):
    rows=cohort(policy);ref=build_reference(rows,policy=policy,cutoff='2026-10-14T00:00:00Z')
    assert ref==build_reference(list(reversed(rows)),policy=policy,cutoff='2026-10-14T00:00:00Z')
    assert len(ref['cohorts']['fixo']['members'])==20
    later=replace(rows[0],provenance={**rows[0].provenance,'played_at':'2026-10-15T00:00:00Z'})
    assert build_reference([*rows[1:],later],policy=policy,cutoff='2026-10-14T00:00:00Z')['cohorts']['fixo']['eligible_player_matches']==19
    with pytest.raises(ValueError):build_reference([rows[0],replace(rows[1],time_basis='running_clock')],policy=policy,cutoff='2026-10-14T00:00:00Z')
    with pytest.raises(ValueError):build_reference([rows[0],rows[0]],policy=policy,cutoff='2026-10-14T00:00:00Z')


def test_invalid_policy_weights_are_rejected(policy):
    broken=deepcopy(policy);broken['roles']['fixo']['Defence']=.6
    with pytest.raises(ValueError):validate_policy(broken)
    broken=deepcopy(policy);broken['components']['Defence']['duel_win_pct']=-.1
    with pytest.raises(ValueError):validate_policy(broken)


def test_ratio_prior_uses_reference_ratio_of_sums(policy):
    rows=cohort(policy)
    rows=[replace(r,facts={**r.facts,'pass_completion_pct':MetricFact(90,9,10,'percent','complete',None)}) for r in rows]
    ref=build_reference(rows,policy=policy,cutoff='2026-10-14T00:00:00Z')
    features=complete_features();features['pass_completion_pct']=MetricFact(100,1,1,'percent','complete',None)
    result=score_match(features,role='fixo',policy=policy,reference=ref)
    assert result['smoothed']['pass_completion_pct']==pytest.approx(1000/11)
    assert ref['cohorts']['fixo']['metrics']['pass_completion_pct']['mean']==.9


def test_policy_weight_sensitivity_exposes_change_in_rank(policy):
    rows=cohort(policy)
    varied=[]
    for i,row in enumerate(rows):
        varied.append(replace(row,facts={k:MetricFact(i if k=='npg_rate10' else 20-i if k=='recoveries_rate10' else f.value,
            i if k=='npg_rate10' else 20-i if k=='recoveries_rate10' else f.numerator,f.denominator,f.unit,f.completeness,f.reason)
            for k,f in row.facts.items()}))
    ref=build_reference(varied,policy=policy,cutoff='2026-10-14T00:00:00Z')
    values=[score_match(r.facts,role='fixo',policy=policy,reference=ref)['score'] for r in varied]
    changed=deepcopy(policy);changed['roles']['fixo']['Finishing']+=.05;changed['roles']['fixo']['Defence']-=.05
    # A changed policy creates a different edition, even if reusing the same raw cohort.
    newref=build_reference(varied,policy=changed,cutoff='2026-10-14T00:00:00Z')
    newvalues=[score_match(r.facts,role='fixo',policy=changed,reference=newref)['score'] for r in varied]
    assert max(abs(a-b) for a,b in zip(values,newvalues))>0
    assert newref['reference_version']!=ref['reference_version']


def test_all_reference_zero_opportunities_stay_neutral_without_fake_percent(policy):
    rows=cohort(policy,role='goalkeeper')
    no_shots=MetricFact(None,0,0,'percent','complete','no_opportunities')
    rows=[replace(r,facts={**r.facts,'save_pct':no_shots}) for r in rows]
    ref=build_reference(rows,policy=policy,cutoff='2026-10-14T00:00:00Z')
    assert ref['cohorts']['goalkeeper']['metrics']['save_pct']['mean'] is None
    result=score_match(rows[0].facts,role='goalkeeper',policy=policy,reference=ref)
    assert result['feature_scores']['save_pct']==50 and result['score']==50


def test_reference_rejects_missing_exposure_and_different_policy_edition(policy):
    rows=cohort(policy)
    changed=replace(rows[0],facts={**rows[0].facts,'npg_rate10':MetricFact(1,1,None,'count/10min','complete',None)})
    with pytest.raises(ValueError):build_reference([changed,*rows[1:]],policy=policy,cutoff='2026-10-14T00:00:00Z')
    ref=reference(policy);new=deepcopy(policy);new['ratio_prior_strength']=11
    with pytest.raises(ValueError):score_match(complete_features(),role='fixo',policy=new,reference=ref)
