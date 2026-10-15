"""Deterministic, inspectable pilot heuristic. Never reweights missing data."""
import math
from hashlib import sha256
import json
from aifootball.ratings.registry import REGISTRY,REGISTRY_VERSION


def policy_hash(policy):return sha256(json.dumps(policy,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def validate_policy(policy):
    def weights(values):
        if not values or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values.values()) or not math.isclose(sum(values.values()),1,abs_tol=1e-9):
            raise ValueError('Policy weights must be finite, nonnegative and sum to one')
    if policy.get('physical_weight')!=0 or policy.get('missing_reweighting') is not False:raise ValueError('Physical weight and missing reweighting are not supported')
    if policy.get('registry_version')!=REGISTRY_VERSION:raise ValueError('Unknown metric registry')
    for component,values in policy['components'].items():
        weights(values)
        if not set(values)<=set(REGISTRY):raise ValueError('Unknown component metric')
    for role,values in policy['roles'].items():
        weights(values)
        if set(values)!=set(policy['components']):raise ValueError('Incomplete component weight map')
    for key,spec in REGISTRY.items():
        if policy['directions'].get(key)!=spec['direction']:raise ValueError('Metric direction conflicts with registry')
    for key in ('reference_min_players','reference_min_player_matches','tournament_min_matches'):
        if type(policy[key]) is not int or policy[key]<1:raise ValueError('Invalid cohort threshold')
    for key in ('ratio_prior_strength','match_min_minutes','tournament_min_minutes','tournament_prior_weight'):
        if type(policy[key]) not in (int,float) or not math.isfinite(policy[key]) or policy[key]<=0:raise ValueError('Invalid policy threshold')
    for key,maximum in (('coverage_min',1),('tournament_prior_score',100)):
        if type(policy[key]) not in (int,float) or not math.isfinite(policy[key]) or not 0<=policy[key]<=maximum:raise ValueError('Invalid policy range')
    return policy


def required_metrics(policy,role):
    return set().union(*(policy['components'][c] for c,w in policy['roles'].get(role,{}).items() if w>0))


def validate_feature(fact,key):
    if fact.unit!=REGISTRY[key]['unit']:raise ValueError('Feature unit differs from registry')
    if fact.completeness=='complete':
        if fact.numerator is None or fact.denominator is None:raise ValueError('Complete normalized fact requires numerator and exposure')
        if fact.denominator==0 and (fact.value is not None or fact.numerator!=0):raise ValueError('Zero opportunities cannot have a measured value')
        if fact.unit=='percent' and fact.numerator>fact.denominator:raise ValueError('Invalid percentage facts')


def usable(fact):
    return fact is not None and fact.completeness=='complete' and (fact.value is not None or fact.reason=='no_opportunities' and fact.denominator==0 and fact.numerator==0)


def percentile(value:float,values:list[float],*,lower_is_better=False)->float:
    if type(value) not in (int,float) or not math.isfinite(value) or not values or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
        raise ValueError('Percentile requires finite observations')
    p=100*(sum(v<value for v in values)+.5*sum(v==value for v in values))/len(values)
    return 100-p if lower_is_better else p


def score_match(features,*,role,policy,reference):
    validate_policy(policy)
    if reference.get('policy_hash')!=policy_hash(policy):raise ValueError('Reference belongs to a different policy edition')
    result={'score':None,'display_rating':None,'components':{},'contributions':{},'feature_scores':{},'smoothed':{},
        'reasons':[],'eligible':False,'model_version':policy['model_version'],'reference_version':reference['reference_version'],
        'profile_id':reference['profile_id'],'time_basis':reference['time_basis'],'role':role}
    if role not in policy['roles']:result['reasons'].append('unknown_role');return result
    cohort=reference.get('cohorts',{}).get(role,{})
    if not cohort.get('available'):result['reasons'].append('insufficient_reference');return result
    needed=required_metrics(policy,role)
    for key in sorted(needed):
        fact=features.get(key);metric=cohort['metrics'].get(key)
        if not usable(fact) or not metric:
            result['feature_scores'][key]=None;result['reasons'].append('missing:'+key);continue
        validate_feature(fact,key)
        if fact.denominator==0 and fact.reason=='no_opportunities':result['feature_scores'][key]=50;continue
        if fact.unit=='percent':
            if fact.numerator is None or fact.denominator is None or fact.numerator>fact.denominator:raise ValueError('Invalid percentage facts')
            if metric['mean'] is None:
                result['feature_scores'][key]=50;continue
            strength=policy['ratio_prior_strength']
            value=100*(fact.numerator+strength*metric['mean'])/(fact.denominator+strength)
            result['smoothed'][key]=value
        else:value=fact.value
        if not metric['values']:
            result['feature_scores'][key]=None;result['reasons'].append('no_reference_observations:'+key);continue
        result['feature_scores'][key]=percentile(value,metric['values'],lower_is_better=policy['directions'][key]=='bad')
    for component,weight in policy['roles'][role].items():
        if weight==0:continue
        parts=policy['components'][component]
        value=None if any(result['feature_scores'].get(k) is None for k in parts) else sum(w*result['feature_scores'][k] for k,w in parts.items())
        result['components'][component]=value
        result['contributions'][component]=None if value is None else value*weight
    if not result['reasons']:
        result['score']=sum(result['contributions'].values());result['display_rating']=round(1+9*result['score']/100,1);result['eligible']=True
    return result
