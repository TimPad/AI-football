"""Pure metrics over one selected, verified role/time/source edition.

Provenance carries per-player/role category completeness, covered role and play
intervals, source scope, clock basis and actual hall geometry. A service adapter
must intersect category declarations with these ranges; processing completion
or model confidence never supplies a completeness declaration.
"""
from collections import defaultdict
from aifootball.ratings.schema import MetricFact,MatchPerformance
from aifootball.ratings.registry import REGISTRY
from aifootball.ratings.actions import discipline_cost,valid_block_link


def _missing(numerator,denominator,unit,reason,completeness='unknown'):
    return MetricFact(None,numerator,denominator,unit,completeness,reason)


def _ratio(numerator,denominator,unit,complete,*,unresolved=0):
    if not complete:return _missing(numerator,denominator,unit,'incomplete_category','partial')
    if denominator is None:return _missing(numerator,None,unit,'unknown_exposure')
    if denominator==0:return _missing(numerator,0,unit,'unresolved_attempts' if unresolved else 'no_opportunities','complete')
    return MetricFact((600 if unit=='count/10min' else 100)*numerator/denominator,numerator,denominator,unit,'complete',None)


def _in(time,ranges):return ranges is not None and any(a<=time<b for a,b in ranges)


def build_features(performance:MatchPerformance,actions:list[dict],*,profile_id:str)->dict[str,MetricFact]:
    if profile_id not in ('per10','per10-possession'):raise ValueError('Unknown metric profile')
    p=performance;meta=p.provenance;pid=p.player_id;side=meta.get('side');facts={}
    ranges=meta.get('eligible_intervals');roles=meta.get('role_intervals');clock=meta.get('clock_basis')
    permitted=meta.get('source_kind')=='manual_verified' or (meta.get('source_kind')=='reviewed_video' and meta.get('analysis_scope')=='full_match')
    categories=meta.get('categories',{})
    def complete(*names):return permitted and all(categories.get(n)=='complete' for n in names)
    valid=[a for a in actions if a.get('verified') and a.get('kind') not in ('shootout_attempt','goal_candidate')]
    def located(a):
        t=a.get('start_ms')
        if a.get('clock_basis',clock)!=clock:return False
        if t is None:return bool(meta.get('single_role')) and (a.get('role') in (None,p.role))
        return _in(t,roles) and _in(t,ranges)
    own=[a for a in valid if a.get('player_id')==pid and located(a)]
    uncertain={a['kind'] for a in valid if a.get('player_id')==pid and (a.get('start_ms') is None and not meta.get('single_role') or a.get('clock_basis',clock)!=clock)}
    def category_ok(names,kinds):
        unidentified=any(a['kind'] in kinds and a.get('player_id') is None and a.get('side') in (side,None) for a in valid)
        return complete(*names) and not uncertain.intersection(kinds) and not unidentified
    def exposure(feature):
        denom=REGISTRY[feature]['denominator']
        return meta.get(denom) if profile_id=='per10-possession' and denom in ('possession_s','without_possession_s') else p.eligible_play_s
    def count_rate(stem,feature,count,known):
        facts[stem+'_known_count']=MetricFact(count,count,None,'count','complete',None)
        facts[stem+'_count']=MetricFact(count,count,None,'count','complete',None) if known else _missing(count,None,'count','incomplete_category','partial')
        facts[feature]=_ratio(count,exposure(feature),'count/10min',known)
    def percentage(stem,feature,items,known,field='success'):
        resolved=[a for a in items if type(a.get(field)) is bool];unresolved=len(items)-len(resolved)
        n=sum(a[field] for a in resolved);d=len(resolved)
        facts[stem+'_unresolved_count']=MetricFact(unresolved,unresolved,None,'count','complete',None)
        if feature=='shots_on_target_pct' and unresolved:
            facts[feature]=_missing(n,len(items),'percent','unresolved_attempts','partial')
        else:facts[feature]=_ratio(n,d,'percent',known,unresolved=unresolved)
    goals=[a for a in valid if a['kind']=='goal' and not a.get('own_goal') and a.get('side') in (side,None)]
    unknown_goals=any(a.get('player_id') is None for a in goals)
    npg=sum(a.get('non_penalty_goal',not a.get('from_penalty')) for a in own if a['kind']=='goal' and not a.get('own_goal'))
    count_rate('npg','npg_rate10',npg,category_ok(['goals'],{'goal'}) and not unknown_goals)
    assists=[a for a in goals if a.get('assist_id')==pid and a.get('assist_known') and located(a)]
    assist_known=all(a.get('assist_known') for a in goals)
    count_rate('assists','assists_rate10',len(assists),complete('assists','goals') and assist_known and not any(a.get('assist_id')==pid and (a.get('start_ms') is None and not meta.get('single_role') or a.get('clock_basis',clock)!=clock) for a in goals))
    shots=[a for a in own if a.get('counts_as_shot',a['kind']=='shot' or a['kind']=='goal' and not a.get('own_goal'))]
    percentage('shots_on_target','shots_on_target_pct',shots,category_ok(['shots','goals'],{'shot','goal'}) and not unknown_goals,'on_target')
    percentage('pass_completion','pass_completion_pct',[a for a in own if a['kind']=='pass'],category_ok(['passes'],{'pass'}))
    percentage('duel_win','duel_win_pct',[a for a in own if a['kind']=='duel'],category_ok(['duels'],{'duel'}))
    percentage('distribution','distribution_pct',[a for a in own if a['kind']=='distribution'],category_ok(['distribution'],{'distribution'}))
    for stem,feature,kind,category in [('recoveries','recoveries_rate10','recovery','recoveries'),('blocks','blocks_rate10','shot_block','shot_blocks')]:
        items=[a for a in own if a['kind']==kind]
        by_id={a['id']:a for a in valid}
        linked=all(valid_block_link(a,by_id.get(a.get('shot_id'))) for a in items) if kind=='shot_block' else True
        count_rate(stem,feature,len(items),category_ok([category],{kind}) and linked)
    # A possession chain is local to the same verified clock, never across gaps.
    last=None;keypasses=[];chain_unknown=False
    potential_passes=[a for a in own if a['kind']=='pass' and a.get('success') is True]
    team_shots=[a for a in valid if a.get('side')==side and a.get('counts_as_shot',a['kind']=='shot' or a['kind']=='goal' and not a.get('own_goal'))]
    if potential_passes and team_shots and (any(not a.get('possession_id') for a in potential_passes) or any(not a.get('possession_id') for a in team_shots)):
        chain_unknown=True
    timed=sorted(valid,key=lambda a:(a.get('start_ms') is None,a.get('start_ms') or 0,a['id']))
    for a in timed:
        if a.get('clock_basis',clock)!=clock or a.get('start_ms') is None or a.get('chain_complete') is False:
            if a.get('player_id')==pid and a['kind']=='pass':chain_unknown=True
            last=None;continue
        if a.get('counts_as_shot',a['kind']=='shot' or a['kind']=='goal' and not a.get('own_goal')):
            if last and last.get('possession_id') and last['possession_id']==a.get('possession_id') and last.get('side')==a.get('side'):
                keypasses.append(last)
            last=None
        elif a['kind']=='pass':
            if a.get('player_id')==pid and a.get('success') is None:chain_unknown=True
            last=a if a.get('success') is True else None
        elif a['kind'] in ('turnover','recovery','duel','error') or last and (a.get('side')!=last.get('side') or a.get('possession_id')!=last.get('possession_id')):last=None
    count_rate('key_pass','key_pass_rate10',sum(a.get('player_id')==pid and located(a) for a in keypasses),category_ok(['passes','shots'],{'pass','shot'}) and not chain_unknown)
    length=(meta.get('pitch') or {}).get('length_m');progression=0;progress_known=True;danger=0;danger_known=True
    for a in own:
        if a['kind'] not in ('pass','carry','distribution','turnover'):continue
        if a['kind']!='turnover' and a.get('success') is False:continue
        direction=a.get('attacking_direction');point=a.get('start_xy');end=a.get('end_xy')
        geometry=length is not None and length>0 and direction in ('left','right') and point is not None
        if a['kind']=='turnover':
            if not geometry or not a.get('opponent_id'):danger_known=False;continue
            x=point[0] if direction=='right' else length-point[0]
            if x<length/4:danger+=1
        else:
            if not geometry or end is None or a.get('success') is not True:progress_known=False;continue
            x=point[0] if direction=='right' else length-point[0];y=end[0] if direction=='right' else length-end[0]
            if int(min(y,length-1e-9)//(length/4))>int(min(x,length-1e-9)//(length/4)):progression+=1
    count_rate('progression','progression_rate10',progression,category_ok(['passes','carries','distribution'],{'pass','carry','distribution'}) and progress_known)
    count_rate('dangerous_turnover','dangerous_turnover_rate10',danger,category_ok(['turnovers'],{'turnover'}) and danger_known)
    unknown_discipline=any(a['kind'] in ('foul','card','error') and a.get('side')==side and a.get('player_id') is None for a in valid)
    count_rate('discipline_cost','discipline_cost_rate10',discipline_cost(own,pid),category_ok(['fouls','cards','errors'],{'foul','card','error'}) and not unknown_discipline)
    saves=[a for a in own if a['kind']=='save' and a.get('success') is True]
    conceded=[a for a in valid if a['kind']=='goal' and a.get('side')!=side and not a.get('own_goal') and a.get('start_ms') is not None and located(a)]
    unknown_faced=any(a['kind']=='goal' and a.get('side')!=side and not a.get('own_goal') and a.get('start_ms') is None for a in valid)
    unresolved_saves=sum(a['kind']=='save' and a.get('success') is None for a in own)
    gk_known=p.role=='goalkeeper' and meta.get('presence_verified') and category_ok(['saves','goals'],{'save'}) and not unknown_faced
    facts['save_unresolved_count']=MetricFact(unresolved_saves,unresolved_saves,None,'count','complete',None)
    facts['save_pct']=_missing(len(saves),len(saves)+len(conceded)+unresolved_saves,'percent','unresolved_attempts','partial') if unresolved_saves else _ratio(len(saves),len(saves)+len(conceded),'percent',gk_known)
    return {**p.facts,**facts}


def combine_rate(rows:list[MetricFact])->MetricFact:
    if not rows:return _missing(None,None,'count/10min','no_observations')
    unit=rows[0].unit
    if any(v.unit!=unit for v in rows):raise ValueError('Incompatible units')
    if unit not in ('count/10min','percent'):raise ValueError('Not a rate')
    numerator=sum(v.numerator or 0 for v in rows)
    if any(v.completeness!='complete' or v.numerator is None or v.denominator is None or v.value is None and v.reason!='no_opportunities' for v in rows):
        return _missing(numerator,None,unit,'incomplete_aggregate','partial')
    return _ratio(numerator,sum(v.denominator for v in rows),unit,True)


def aggregate_facts(rows:list[MatchPerformance])->dict[str,MetricFact]:
    if not rows:return {}
    editions={(r.tournament_id,r.role,r.time_basis,r.provenance.get('profile_id')) for r in rows}
    if len(editions)>1:raise ValueError('Incompatible performance editions')
    if len({r.match_id for r in rows})!=len(rows):raise ValueError('Select one source per player/match/role before aggregating')
    if len({r.player_id for r in rows})!=1:raise ValueError('Aggregate one player at a time')
    keys=set().union(*(r.facts for r in rows));result={}
    for key in keys:
        values=[r.facts.get(key) for r in rows];known=[v for v in values if v is not None];unit=known[0].unit
        if any(v.unit!=unit for v in known):raise ValueError('Incompatible units')
        if len(known)!=len(values):result[key]=_missing(None,None,unit,'missing_match_category');continue
        if unit in ('percent','count/10min'):result[key]=combine_rate(known)
        elif unit.startswith('heatmap'):result[key]=_missing(None,None,unit,'maps_require_explicit_geometry_and_orientation_normalization')
        elif any(v.value is None or v.completeness!='complete' for v in known):result[key]=_missing(sum(v.numerator or 0 for v in known),None,unit,'incomplete_aggregate','partial')
        else:
            value=max(v.value for v in known) if key in ('vmax_ms','sustained_vmax_ms') else sum(v.value for v in known)
            result[key]=MetricFact(value,value,None,unit,'complete',None)
    return result
