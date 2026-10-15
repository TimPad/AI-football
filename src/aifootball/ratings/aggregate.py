"""One selected source per match, role-weighted scores and capped shrinkage."""
from collections import defaultdict
from copy import deepcopy
import math
from aifootball.ratings.scoring import validate_policy

EDITION=('model_version','reference_version','profile_id','time_basis')


def _number(value,maximum=None):
    if type(value) not in (int,float) or not math.isfinite(value) or value<0 or maximum is not None and value>maximum:raise ValueError('Invalid score or exposure')


def _compatible(rows):
    if len({tuple(r.get(k) for k in EDITION) for r in rows})>1:raise ValueError('Incompatible rating editions')
    if len({r.get('player_id') for r in rows})>1:raise ValueError('Aggregate one player at a time')
    by_match=defaultdict(list)
    for row in rows:by_match[row['match_id']].append(row)
    for group in by_match.values():
        if len({r.get('role') for r in group})!=len(group):raise ValueError('Duplicate player/match/role; select one source first')
        if len({r.get('selected_source') for r in group})>1:raise ValueError('Multiple selected source editions for one match')
    return by_match


def tournament_rating(matches:list[dict],*,prior_score=50,prior_weight=3,match_min_minutes=3,coverage_min=.8)->dict:
    _number(prior_score,100);_number(prior_weight);_number(match_min_minutes);_number(coverage_min,1)
    if prior_weight<=0:raise ValueError('Prior weight must be positive')
    groups=_compatible(matches);summaries=[];known_played=0;unknown_time=False;total_eligible=0;rated_minutes=0
    for mid,group in sorted(groups.items()):
        # Cancelled/technical games and confirmed non-appearances do not add time.
        group=[r for r in group if r.get('status') not in ('cancelled','canceled') and r.get('result_type','played')=='played' and r.get('appeared',True) is not False]
        if not group:continue
        played=[];eligible=[];rated=[];unknown=False
        for row in group:
            minutes=row.get('eligible_play_minutes');played_minutes=row.get('played_minutes',minutes)
            if minutes is not None:_number(minutes)
            if played_minutes is not None:_number(played_minutes)
            if minutes is not None and played_minutes is not None and minutes>played_minutes+1e-8:raise ValueError('Eligible role time exceeds played time')
            if row.get('appeared',True) is None or played_minutes is None:unknown=True
            played.append(played_minutes);eligible.append(minutes)
            score=row.get('score')
            if score is not None:
                _number(score,100)
                if minutes is not None and minutes>0:rated.append((minutes,score))
        total=None if unknown else sum(played)
        all_eligible=None if any(v is None for v in eligible) else sum(eligible)
        known=sum(v or 0 for v in played);known_played+=known;unknown_time|=unknown
        total_eligible+=sum(v or 0 for v in eligible)
        scored_time=sum(t for t,s in rated);coverage=None if total is None else min(1,scored_time/total) if total else None
        # The service preserves whole-match exposure on positional projections.
        whole=max((r.get('match_eligible_play_minutes') or 0 for r in group),default=0) or all_eligible
        valid=whole is not None and whole>=match_min_minutes and coverage is not None and coverage>=coverage_min and scored_time>0
        score=sum(t*s for t,s in rated)/scored_time if valid else None
        weight=min(scored_time/10,1) if valid else 0
        if valid:rated_minutes+=scored_time
        summaries.append({'match_id':mid,'score':score,'eligible_play_minutes':all_eligible,'played_minutes':total,
            'rated_minutes':scored_time if valid else 0,'coverage':coverage,'weight':weight,
            'appeared':any(r.get('appeared',True) is True for r in group)})
    weight_sum=sum(r['weight'] for r in summaries)
    score=(sum(r['weight']*r['score'] for r in summaries if r['weight'])+prior_weight*prior_score)/(weight_sum+prior_weight) if weight_sum else None
    return {'score':score,'display_rating':None if score is None else round(1+9*score/100,1),
        'match_count':sum(r['appeared'] for r in summaries),'rated_match_count':sum(r['weight']>0 for r in summaries),
        'eligible_play_minutes':total_eligible,'played_minutes':None if unknown_time else known_played,
        'known_played_minutes':known_played,'rated_minutes':rated_minutes,'weight_sum':weight_sum,
        'coverage':None if unknown_time or known_played==0 else min(1,rated_minutes/known_played),
        'baseline_influence':None if not weight_sum else prior_weight/(prior_weight+weight_sum),'matches':summaries}


def rank_players(rows:list[dict],*,role:str|None,policy:dict)->list[dict]:
    validate_policy(policy)
    if role is not None and role not in policy['roles']:raise ValueError('Unknown positional ranking')
    if len({tuple(r.get(k) for k in EDITION) for r in rows})>1:raise ValueError('Ranking must use one immutable edition')
    # Preserve original match duration so a short positional segment is not
    # mistaken for a short appearance after applying a position filter.
    total_time=defaultdict(list)
    for r in rows:total_time[(r['player_id'],r['match_id'])].append(r.get('eligible_play_minutes'))
    by_player=defaultdict(list)
    for original in rows:
        if role is not None and original.get('role')!=role:continue
        row=deepcopy(original);values=total_time[(row['player_id'],row['match_id'])]
        row['match_eligible_play_minutes']=None if any(v is None for v in values) else sum(values)
        by_player[row['player_id']].append(row)
    result=[]
    for pid,matches in by_player.items():
        value=tournament_rating(matches,prior_score=policy['tournament_prior_score'],prior_weight=policy['tournament_prior_weight'],
            match_min_minutes=policy['match_min_minutes'],coverage_min=policy['coverage_min'])
        qualified=value['score'] is not None and value['rated_match_count']>=policy['tournament_min_matches'] and value['eligible_play_minutes']>=policy['tournament_min_minutes'] and value['coverage'] is not None and value['coverage']>=policy['coverage_min']
        value.update(player_id=pid,role=role,rank=None,qualification='qualified' if qualified else 'unknown' if value['coverage'] is None else 'preliminary')
        result.append(value)
    result.sort(key=lambda r:(r['qualification']!='qualified',r['score'] is None,-(r['score'] or 0),r['player_id']))
    last=None;place=0
    for index,row in enumerate((r for r in result if r['qualification']=='qualified'),1):
        if row['score']!=last:place=index;last=row['score']
        row['rank']=place
    return result
