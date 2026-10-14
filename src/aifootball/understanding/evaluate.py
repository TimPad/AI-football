"""Offline acceptance metrics. No API, database, or model dependencies."""
import math
import re
from aifootball.understanding.schema import EVENT_KINDS


def _ranges(items):
    result=[]
    for pair in sorted(items):
        if len(pair)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in pair) or pair[0]>=pair[1]:
            raise ValueError('Invalid evaluation interval')
        if result and pair[0]<result[-1][1]:raise ValueError('Overlapping evaluation intervals')
        result.append(pair)
    return result


def _overlap(a,b):return max(0,min(a[1],b[1])-max(a[0],b[0]))
def _ratio(a,b):return a/b if b else None


def _match(predicted,truth,distance,tolerance):
    """Maximum-cardinality bipartite matching, nearest edges first, each GT once."""
    edges={i:sorted((j for j,t in enumerate(truth) if distance(p,t)<=tolerance),key=lambda j:distance(p,truth[j])) for i,p in enumerate(predicted)}
    assigned={}
    def augment(i,seen):
        for j in edges[i]:
            if j in seen:continue
            seen.add(j)
            if j not in assigned or augment(assigned[j],seen):assigned[j]=i;return True
        return False
    for i in sorted(edges,key=lambda i:len(edges[i])):augment(i,set())
    return [(i,j) for j,i in assigned.items()]


def evaluate_understanding(predicted:dict,labels:dict,*,tolerance_ms=2000)->dict:
    source=labels.get('source_sha256')
    if type(source) is not str or not re.fullmatch('[0-9a-f]{64}',source) or predicted.get('source',{}).get('sha256')!=source:
        raise ValueError('Evaluation source hash mismatch')
    if labels.get('split') not in ('tune','control'):raise ValueError('Expected tune or control split')
    if type(tolerance_ms) is not int or tolerance_ms<0:raise ValueError('Invalid tolerance')
    tune=_ranges(labels.get('tune_intervals',[]));control=_ranges(labels.get('control_intervals',[]))
    if any(_overlap(a,b) for a in tune for b in control):raise ValueError('Tune/control intervals overlap')
    # Intervals, when supplied, delimit this evaluation: no matching across splits.
    intervals=tune if labels['split']=='tune' else control
    def included(item):
        a=item.get('start_ms',item.get('video_ms',0));b=item.get('end_ms',a)
        return not intervals or any(x<=a and b<=y for x,y in intervals)
    events={}
    distance=lambda p,t:max(abs(p['start_ms']-t['start_ms']),abs(p['end_ms']-t['end_ms']))
    for kind in sorted(EVENT_KINDS):
        p=[e for e in predicted.get('events',[]) if e['kind']==kind and included(e)]
        t=[e for e in labels.get('events',[]) if e['kind']==kind and included(e)]
        pairs=_match(p,t,distance,tolerance_ms)
        error=sum((abs(p[i]['start_ms']-t[j]['start_ms'])+abs(p[i]['end_ms']-t[j]['end_ms']))/2 for i,j in pairs)
        events[kind]={'gt_count':len(t),'predicted_count':len(p),'tp':len(pairs),'fp':len(p)-len(pairs),'fn':len(t)-len(pairs),
                      'precision':_ratio(len(pairs),len(p)),'recall':_ratio(len(pairs),len(t)),
                      'mean_boundary_error_ms':_ratio(error,len(pairs))}
    truth=[o for o in labels.get('observations',[]) if included(o)];unknown=sum(o.get('number') is None for o in truth)
    numbered=[o for o in truth if o.get('number') is not None];observations=[o for o in predicted.get('observations',[]) if included(o) and o.get('number') is not None]
    pairs=_match(observations,numbered,lambda p,t:abs(p['video_ms']-t['video_ms']) if p['track_id']==t['track_id'] else float('inf'),tolerance_ms)
    correct=sum(observations[i]['number']==numbered[j]['number'] for i,j in pairs)
    identities={}
    for observation in truth:
        if observation.get('player_id') is not None:
            identities.setdefault(observation['track_id'],set()).add(observation['player_id'])
    conflicting={tid for tid,people in identities.items() if len(people)>1}
    suggestions=[s for s in predicted.get('identity_suggestions',[]) if s.get('player_id') is not None and s['track_id'] in identities]
    hits=sum(s['track_id'] not in conflicting and s['player_id'] in identities[s['track_id']] for s in suggestions)
    covered=_ranges(predicted.get('coverage',{}).get('covered_intervals',[]));coverage=_ranges(labels.get('coverage',[]))
    if intervals:coverage=[pair for a in coverage for b in intervals if (pair:=[max(a[0],b[0]),min(a[1],b[1])])[0]<pair[1]]
    total=sum(b-a for a,b in coverage);known=sum(_overlap(a,b) for a in coverage for b in covered)
    labelled=known_state=correct_state=0
    p_states=predicted.get('states',[]);t_states=[s for s in labels.get('states',[]) if included(s)]
    _ranges([[s['start_ms'],s['end_ms']] for s in p_states]);_ranges([[s['start_ms'],s['end_ms']] for s in t_states])
    for t in t_states:
        if t['kind']=='unknown':continue
        labelled+=t['end_ms']-t['start_ms']
        for p in p_states:
            overlap=_overlap([p['start_ms'],p['end_ms']],[t['start_ms'],t['end_ms']])
            if p['kind']!='unknown':known_state+=overlap;correct_state+=overlap*(p['kind']==t['kind'])
    return {'source_sha256':source,'split':labels['split'],'tolerance_ms':tolerance_ms,'events':events,
        'numbers':{'labelled':len(numbered),'observed':len(pairs),'correct':correct,'accuracy':_ratio(correct,len(pairs)),
                   'coverage':_ratio(len(pairs),len(numbered)),'unknown_labels':unknown},
        'identity':{'labelled':len(identities),'suggested':len(suggestions),'correct':hits,'precision':_ratio(hits,len(suggestions)),
                    'coverage':_ratio(len(suggestions),len(identities)),'conflicting_tracks':len(conflicting)},
        'coverage':{'labelled_ms':total,'known_ms':known,'known_fraction':_ratio(known,total)},
        'states':{'labelled_ms':labelled,'known_ms':known_state,'correct_ms':correct_state,'accuracy':_ratio(correct_state,known_state),'coverage':_ratio(known_state,labelled)}}
