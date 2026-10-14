"""Deterministic agreement of already-global window observations."""
from copy import deepcopy
from hashlib import sha256
from aifootball.analytics.exchange import canonical
from aifootball.understanding.schema import require,hash_value,integer


def _union(intervals):
    merged=[]
    for start,end in sorted(intervals):
        if merged and start<=merged[-1][1]:merged[-1][1]=max(end,merged[-1][1])
        else:merged.append([start,end])
    return merged


def _timeline(items,covered,duration,*,phase=False,team=None):
    points=sorted({0,duration,*[point for item in items for point in (item['start_ms'],item['end_ms'])],
                   *[point for pair in covered for point in pair]})
    result=[]
    for start,end in zip(points,points[1:]):
        active=[item for item in items if item['start_ms']<=start and item['end_ms']>=end]
        known={item['kind'] for item in active if item['kind']!='unknown'}
        has_coverage=any(a<=start and b>=end for a,b in covered)
        kind=next(iter(known)) if has_coverage and len(known)==1 else 'unknown'
        evidence=sorted({eid for item in active for eid in item['evidence_ids']})
        limitations=sorted({note for item in active for note in item['limitations']})
        if len(known)>1:limitations.append('Противоречивые наблюдения пересекающихся окон')
        value={'kind':kind,'start_ms':start,'end_ms':end,'evidence_ids':evidence,'limitations':limitations}
        if phase:
            possessions={item['possession'] for item in active if item['possession'] is not None}
            directions={item['attacking_direction'] for item in active if item['attacking_direction']!='unknown'}
            value.update(team=team,possession=next(iter(possessions)) if kind!='unknown' and len(possessions)==1 else None,
                         attacking_direction=next(iter(directions)) if kind!='unknown' and len(directions)==1 else 'unknown')
        if result and {k:v for k,v in result[-1].items() if k not in ('start_ms','end_ms')}=={k:v for k,v in value.items() if k not in ('start_ms','end_ms')}:
            result[-1]['end_ms']=end
        else:result.append(value)
    return result


def reconcile_windows(results,*,duration_ms,source_sha256,prompt_version='futsal-v1'):
    hash_value(source_sha256,'source hash');integer(duration_ms,'duration',1,86400000)
    ordered=sorted(deepcopy(results),key=lambda item:(item['start_ms'],item['end_ms'],item['window_id']))
    ids=set();covered=[];observations=[];states=[];phases=[];candidates=[];summaries=[];evidence={}
    for window in ordered:
        start,end=window['start_ms'],window['end_ms'];doc=window['document']
        require(type(start) is int and type(end) is int and 0<=start<end<=duration_ms,'window bounds')
        require(window['window_id'] not in ids,'duplicate window');ids.add(window['window_id'])
        require(doc.get('time_basis')=='video','global time basis required')
        for kind in ('events','states','phases'):
            for item in doc[kind]:require(start<=item['start_ms']<item['end_ms']<=end,'out-of-window time')
        for item in doc['observations']:require(start<=item['video_ms']<end,'out-of-window observation')
        covered.append([start,end]);observations.extend(doc['observations']);states.extend(doc['states']);phases.extend(doc['phases'])
        for item in window.get('evidence',[]):
            if item['id'] in evidence:require(evidence[item['id']]==item,'conflicting evidence')
            evidence[item['id']]=item
        for item in doc['events']:candidates.append((window['window_id'],item))
        for item in doc['summary']:summaries.append((window['window_id'],item))
    covered=_union(covered);unknown=[];cursor=0
    for start,end in covered:
        if start>cursor:unknown.append([cursor,start])
        cursor=end
    if cursor<duration_ms:unknown.append([cursor,duration_ms])
    groups=[]
    for window_id,item in sorted(candidates,key=lambda pair:(pair[1]['start_ms'],pair[1]['end_ms'],pair[1]['kind'],pair[0],pair[1]['id'])):
        match=None
        for group in groups:
            old=group['event']
            if (window_id not in group['windows'] and old['kind']==item['kind'] and old['team']==item['team'] and
                sorted(old['track_ids'])==sorted(item['track_ids']) and
                max(old['start_ms'],item['start_ms'])<min(old['end_ms'],item['end_ms']) and
                abs(old['start_ms']-item['start_ms'])<=2000 and abs(old['end_ms']-item['end_ms'])<=2000):
                match=group;break
        if match is None:
            match={'event':deepcopy(item),'windows':set(),'source_ids':[]};groups.append(match)
        else:
            old=match['event'];old['start_ms']=min(old['start_ms'],item['start_ms']);old['end_ms']=max(old['end_ms'],item['end_ms'])
            old['evidence_ids']=sorted(set(old['evidence_ids'])|set(item['evidence_ids']))
            old['limitations']=sorted(set(old['limitations'])|set(item['limitations']))
            audio={canonical(value):value for value in old['audio_observations']+item['audio_observations']}
            old['audio_observations']=[audio[key] for key in sorted(audio)]
        match['windows'].add(window_id);match['source_ids'].append((window_id,item['id']))
    events=[];mapping={}
    for group in groups:
        item=group['event'];normalized={key:value for key,value in item.items() if key!='id'}
        normalized['track_ids']=sorted(normalized['track_ids']);normalized['evidence_ids']=sorted(normalized['evidence_ids'])
        identity=sha256(canonical({'source':source_sha256,'prompt':prompt_version,'event':normalized,
                                  'windows':sorted(group['windows'])})).hexdigest()[:32]
        item.update(normalized,id=identity);events.append(item)
        for key in group['source_ids']:mapping[key]=identity
    summary=[];summary_keys=set()
    for window_id,item in summaries:
        refs=[]
        for event_id in item['event_ids']:
            require((window_id,event_id) in mapping,'unknown summary event');refs.append(mapping[(window_id,event_id)])
        require(refs or item['metric_refs'],'ungrounded summary')
        value={**item,'event_ids':sorted(set(refs))};key=canonical(value)
        if key not in summary_keys:summary.append(value);summary_keys.add(key)
    final_phases=[]
    for team in (None,'A','B'):
        members=[phase for phase in phases if phase['team']==team]
        if members:final_phases.extend(_timeline(members,covered,duration_ms,phase=True,team=team))
    dedup={canonical(item):item for item in observations}
    return {'events':sorted(events,key=lambda item:(item['start_ms'],item['id'])),
            'states':_timeline(states,covered,duration_ms),'phases':final_phases,
            'observations':[dedup[key] for key in sorted(dedup)],'summary':summary,
            'evidence':[evidence[key] for key in sorted(evidence)],
            'coverage':{'covered_intervals':covered,'unknown_intervals':unknown,
                        'status':'unavailable' if not covered else 'partial' if unknown else 'complete'}}
