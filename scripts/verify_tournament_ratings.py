"""Independent numerical acceptance on synthetic UUIDs. No database or API key.

The oracle below uses explicit percentile/role-weight equations; expected values
never call the scoring functions. It verifies software arithmetic, not athletes.
"""
from copy import deepcopy
from dataclasses import asdict,replace
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
from aifootball.ratings.schema import MatchPerformance,MetricFact
from aifootball.ratings.actions import canonical_actions
from aifootball.ratings.features import build_features,combine_rate
from aifootball.ratings.reference import build_reference
from aifootball.ratings.scoring import score_match
from aifootball.ratings.aggregate import rank_players,tournament_rating
from aifootball.ratings.explanation import explain_rating
from aifootball.ratings.registry import REGISTRY

ROOT=Path(__file__).resolve().parents[1]
CATEGORIES=('goals','assists','shots','passes','carries','duels','recoveries','shot_blocks','turnovers','fouls','cards','errors','saves','distribution')
WEIGHTS={'fixo':(.10,.40),'ala':(.25,.20),'pivot':(.40,.10),'universal':(.25,.25)}


def uid(value):return str(uuid5(NAMESPACE_URL,'aifootball:rating-acceptance:'+value))


def fixture():
    rows=[];actions_by_key={};expected={}
    for role in ('fixo','ala','pivot','universal','goalkeeper'):
        for ability in range(5):
            pid=uid(f'{role}:person:{ability}')
            for match_index in range(4):
                mid=uid(f'{role}:{ability}:match:{match_index}');opponent=uid('opponent')
                meta={'profile_id':'per10','level':'synthetic','played_at':'2026-10-01T12:00:00Z',
                    'side':'home','clock_basis':'game','analysis_scope':'full_match','source_kind':'manual_verified',
                    'categories':{c:'complete' for c in CATEGORIES},'role_intervals':[[0,600000]],'eligible_intervals':[[0,600000]],
                    'single_role':True,'presence_verified':True,'pitch':{'length_m':42,'width_m':18},
                    'source_version':uid(mid+':source')}
                protocol={'events':[],'clock_basis':'game','period_offsets_ms':{'1':0}}
                manual=[]
                def event(kind,index,**data):return {'id':uid(mid+f':{kind}:{index}'),'kind':kind,'player_id':pid,'side':'home',
                    'clock_basis':'game','start_ms':1000+index*10000,'role':role,**data}
                if role=='goalkeeper':
                    for i in range(ability):manual.append(event('save',i,success=True))
                    for i in range(4-ability):protocol['events'].append(event('goal',i,player_id=opponent,side='away',assist_known=True))
                else:
                    for i in range(ability):
                        protocol['events'].append(event('goal',i,assist_known=True))
                        manual.append(event('recovery',i))
                actions=canonical_actions(protocol,manual,[])
                row=MatchPerformance(uid('tournament'),mid,pid,role,'reviewed_effective',600,600,1,{},meta)
                row=replace(row,facts=build_features(row,actions,profile_id='per10'))
                rows.append(row);actions_by_key[(mid,pid)]=actions
                # Four equal observations at each of five levels: midrank 10,30,...90.
                p=10+20*ability
                expected[(mid,pid)]=50+.6*(p-50) if role=='goalkeeper' else 50+(WEIGHTS[role][0]*.6+WEIGHTS[role][1]*.5)*(p-50)
    return rows,actions_by_key,expected


def sensitivity(policy,rows):
    base=next(r for r in rows if r.role=='fixo');samples=[]
    def facts(i):
        return {k:MetricFact(i,i,600,'count/10min','complete',None) if spec['unit']=='count/10min' else MetricFact(25*i,i,4,'percent','complete',None) for k,spec in REGISTRY.items()}
    for i in range(5):
        for m in range(4):samples.append(replace(base,player_id=uid(f'sensitivity:{i}'),match_id=uid(f'sensitivity:{i}:{m}'),facts=facts(i)))
    a=facts(2);a['duel_win_pct']=facts(1)['duel_win_pct']
    b=facts(2);b['npg_rate10']=facts(0)['npg_rate10']
    results=[]
    for delta in (-.05,0,.05):
        p=deepcopy(policy);p['roles']['fixo']['Finishing']+=delta;p['roles']['fixo']['Defence']-=delta
        ref=build_reference(samples,policy=p,cutoff='2026-10-14T00:00:00Z')
        scores=[score_match(f,role='fixo',policy=p,reference=ref)['score'] for f in (a,b)]
        results.append({'finishing_weight':p['roles']['fixo']['Finishing'],'defence_weight':p['roles']['fixo']['Defence'],
            'scores':scores,'order':'A>B' if scores[0]>scores[1]+1e-9 else 'B>A' if scores[1]>scores[0]+1e-9 else 'tie'})
    assert results[0]['order']=='B>A' and results[1]['order']=='tie' and results[2]['order']=='A>B'
    return {'scenarios':results,'rank_reversals':1,'max_score_change':max(abs(r['scores'][i]-results[1]['scores'][i]) for r in results for i in range(2)),
        'interpretation':'A small weight change can reverse comparable players. This is not sporting calibration.'}


def verify():
    policy=json.loads((ROOT/'configs/ratings/role-profile-v1.json').read_text());rows,actions,expected=fixture()
    reference=build_reference(rows,policy=policy,cutoff='2026-10-14T00:00:00Z')
    assert all(c['available'] and len(c['players'])==5 and c['eligible_player_matches']==20 for c in reference['cohorts'].values())
    values=[];checks=0
    for row in rows:
        ability=int(next(i for i in range(5) if row.player_id==uid(f'{row.role}:person:{i}')))
        assert row.eligible_play_s==600
        if row.role!='goalkeeper':assert row.facts['npg_count'].value==ability and row.facts['recoveries_count'].value==ability
        else:assert row.facts['save_pct'].numerator==ability and row.facts['save_pct'].denominator==4
        result=score_match(row.facts,role=row.role,policy=policy,reference=reference)
        assert result['score'] is not None and abs(result['score']-expected[(row.match_id,row.player_id)])<1e-9
        explanation=explain_rating({**result,'player_id':row.player_id},row.facts,actions[(row.match_id,row.player_id)])
        selected={m['canonical_action_id'] for key in ('positive','errors') for m in explanation[key]}
        assert selected<={a['id'] for a in actions[(row.match_id,row.player_id)] if a.get('player_id')==row.player_id and a.get('role')==row.role}
        values.append({'player_id':row.player_id,'match_id':row.match_id,'role':row.role,'score':result['score'],
            'eligible_play_minutes':10,'played_minutes':10,'appeared':True,'model_version':result['model_version'],
            'reference_version':result['reference_version'],'profile_id':'per10','time_basis':'reviewed_effective'})
        checks+=1
    for role in policy['roles']:
        ranking=rank_players(values,role=role,policy=policy);assert len(ranking)==5 and all(p['qualification']=='qualified' for p in ranking)
        for item in ranking:
            own=[r for r in values if r['player_id']==item['player_id']]
            expected_t=(sum(expected[(r['match_id'],r['player_id'])] for r in own)+150)/7
            assert abs(item['score']-expected_t)<1e-9 and item['match_count']==4
    first=rows[0];events=actions[(first.match_id,first.player_id)]
    for meta in ({**first.provenance,'source_kind':'reviewed_video','analysis_scope':'highlights'},
        {**first.provenance,'categories':{**first.provenance['categories'],'recoveries':'unknown'}}):
        incomplete=replace(first,provenance=meta)
        assert score_match(build_features(incomplete,events,profile_id='per10'),role=first.role,policy=policy,reference=reference)['score'] is None
    unknown=replace(first,eligible_play_s=None,participation_s=None,coverage=None)
    assert score_match(build_features(unknown,events,profile_id='per10'),role=first.role,policy=policy,reference=reference)['score'] is None
    minute=rank_players([{**values[-1],'match_id':'short','eligible_play_minutes':1,'played_minutes':1,'score':100}],role=None,policy=policy)[0]
    assert minute['qualification']!='qualified' and minute['score'] is None
    assert tournament_rating([{'match_id':'one','score':80,'eligible_play_minutes':10}])['score']==57.5
    assert tournament_rating([{'match_id':str(i),'score':80,'eligible_play_minutes':10} for i in range(5)])['score']==68.75
    rate=combine_rate([MetricFact(2,2,600,'count/10min','complete',None),MetricFact(.5,1,1200,'count/10min','complete',None)])
    assert rate.value==600*3/1800==1
    again=build_reference(list(reversed(rows)),policy=policy,cutoff='2026-10-14T00:00:00Z');assert again==reference
    physical=replace(first,facts={**first.facts,'distance_m':MetricFact(100000,100000,None,'m','complete',None)})
    assert score_match(physical.facts,role=first.role,policy=policy,reference=reference)==score_match(first.facts,role=first.role,policy=policy,reference=reference)
    fingerprint=sha256(json.dumps([asdict(r) for r in rows],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'player_matches':len(rows),'players_per_role':5,'player_matches_per_role':20,'independent_formula_checks':checks,
        'source_fingerprint':fingerprint,'reference_version':reference['reference_version'],'sensitivity':sensitivity(policy,rows),
        'sporting_accuracy_verified':False,'scope':'synthetic arithmetic/lineage only','goalkeeper_limitation':'Save percentage does not model shot difficulty; PSxG/GSAA not implemented.'}


if __name__=='__main__':print(json.dumps(verify(),ensure_ascii=False,indent=2))
