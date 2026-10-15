"""Frozen, content-addressed reference cohorts of compatible verified facts."""
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import json
from aifootball.ratings.registry import REGISTRY
from aifootball.ratings.scoring import validate_policy,policy_hash,required_metrics,usable,validate_feature


def _date(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('Reference cutoff and match dates require timezone')
    return result


def build_reference(rows,*,policy,cutoff):
    validate_policy(policy);cutoff_date=_date(cutoff)
    contexts={(r.tournament_id,r.time_basis,r.provenance.get('profile_id'),r.provenance.get('level')) for r in rows}
    if len(contexts)>1:raise ValueError('Reference cannot mix tournament, level, profile or time basis')
    if not contexts:raise ValueError('Reference needs a declared source context')
    tournament,time_basis,profile,level=next(iter(contexts))
    if profile not in policy['profiles'] or not level:raise ValueError('Reference profile and competition level required')
    ids=[(r.match_id,r.player_id,r.role) for r in rows]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate player/match/role observation')
    by_role=defaultdict(list)
    for row in rows:
        if _date(row.provenance['played_at'])>cutoff_date:continue
        if row.role not in policy['roles'] or row.eligible_play_s is None or row.eligible_play_s<60*policy['match_min_minutes'] or row.coverage is None or row.coverage<policy['coverage_min']:continue
        required=required_metrics(policy,row.role)
        if any(not usable(row.facts.get(k)) for k in required):continue
        for key in required:
            f=row.facts[key]
            validate_feature(f,key)
            if f.unit!=REGISTRY[key]['unit']:raise ValueError('Reference units differ from registry')
            if f.unit=='percent' and (f.numerator is None or f.denominator is None or f.numerator>f.denominator):raise ValueError('Invalid reference ratio')
        by_role[row.role].append(row)
    result={'model_version':policy['model_version'],'policy_hash':policy_hash(policy),'profile_id':profile,'time_basis':time_basis,
        'tournament_id':tournament,'level':level,'cutoff':cutoff,'cohorts':{}}
    for role in policy['roles']:
        selected=sorted(by_role[role],key=lambda r:(r.match_id,r.player_id));players=sorted({r.player_id for r in selected});metrics={}
        for key in sorted(required_metrics(policy,role)):
            facts=[r.facts[key] for r in selected];percent=REGISTRY[key]['unit']=='percent'
            numerator=sum(f.numerator or 0 for f in facts);denominator=sum(f.denominator or 0 for f in facts)
            mean=numerator/denominator if percent and denominator else None
            strength=policy['ratio_prior_strength']
            values=[100*(f.numerator+strength*mean)/(f.denominator+strength) if percent else f.value for f in facts if f.denominator!=0 and f.value is not None] if not percent or mean is not None else []
            metrics[key]={'unit':REGISTRY[key]['unit'],'mean':mean,'values':sorted(values),'numerator':numerator,'denominator':denominator}
        result['cohorts'][role]={'available':len(players)>=policy['reference_min_players'] and len(selected)>=policy['reference_min_player_matches'],
            'eligible_player_matches':len(selected),'players':players,'metrics':metrics,
            'members':[{'match_id':r.match_id,'player_id':r.player_id,'role':r.role,'eligible_play_s':r.eligible_play_s,
                'coverage':r.coverage,'source_version':r.provenance.get('source_version'),
                'facts':{k:asdict(r.facts[k]) for k in sorted(required_metrics(policy,role))}} for r in selected]}
    result['reference_version']=sha256(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return result
