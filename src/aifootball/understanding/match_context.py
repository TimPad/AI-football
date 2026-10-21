"""Source-bound operator facts and an unverified, bounded VLM history."""
from copy import deepcopy
from hashlib import sha256
import math
import re

from aifootball.analytics.exchange import canonical

FACTS={'match_status','team_A_color','team_B_color','pitch_dimensions_m','period','regulation','goal_orientation'}


def validate_passport(document,source_sha256):
    def require(value):
        if not value:raise ValueError('invalid match passport')
    require(type(document) is dict and set(document)=={'schema_version','source_sha256','sport','scope','facts'})
    require(type(source_sha256) is str and re.fullmatch('[0-9a-f]{64}',source_sha256))
    require(document['schema_version']=='match-passport-v1' and document['source_sha256']==source_sha256)
    require(document['sport']=='futsal' and document['scope'] in ('full_match','continuous_excerpt','highlights','unknown'))
    require(type(document['facts']) is dict and set(document['facts'])<=FACTS)
    result=deepcopy(document)
    for name in FACTS:
        fact=result['facts'].setdefault(name,None)
        if fact is None:continue
        require(type(fact) is dict and set(fact)=={'value','origin','reference'})
        require(fact['origin'] in ('catalog_snapshot','operator_review'))
        require(type(fact['reference']) is str and 0<len(fact['reference'])<=200)
        value=fact['value']
        if name=='match_status':require(value in ('pre_match','in_progress','break','finished'))
        elif name.startswith('team_'):require(type(value) is str and 0<len(value)<=40)
        elif name=='period':require(type(value) is int and 1<=value<=4)
        elif name=='pitch_dimensions_m':
            require(type(value) is dict and set(value)=={'length_m','width_m'})
            require(all(type(v) in (int,float) and math.isfinite(v) and 1<v<=200 for v in value.values()))
        elif name=='regulation':
            require(type(value) is dict and set(value)=={'half_duration_s','clock_type'})
            require(type(value['half_duration_s']) is int and 60<=value['half_duration_s']<=7200)
            require(value['clock_type'] in ('effective','running','unknown'))
        elif name=='goal_orientation':
            require(type(value) is dict and set(value)=={'left_goal','right_goal'})
            for box in value.values():
                require(type(box) is list and len(box)==4)
                require(all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in box))
                require(box[0]<box[2] and box[1]<box[3])
    require(len(canonical(result))<=3000)
    return result


def merged_intervals(intervals):
    result=[]
    for start,end in sorted(intervals):
        if result and start<=result[-1][1]:result[-1][1]=max(result[-1][1],end)
        else:result.append([start,end])
    return result


class MatchChronology:
    def __init__(self,source_sha256,passport):
        self.source=source_sha256;self.passport=validate_passport(passport,source_sha256)
        self._windows={};self._gaps={}

    def add(self,window,document,request_key):
        if not 0<=window.start_ms<window.end_ms:raise ValueError('invalid window')
        duration=window.end_ms-window.start_ms
        digest=sha256(canonical(document)).hexdigest()
        key=sha256(canonical([self.source,window.id,window.start_ms,window.end_ms,request_key])).hexdigest()[:24]
        if key in self._windows:
            if self._windows[key]['document_sha256']!=digest:raise ValueError('conflicting replay')
            return
        record={'id':key,'source_window_id':window.id,'start_ms':window.start_ms,'end_ms':window.end_ms,
                'request_key':request_key,'document_sha256':digest,'events':[],'states':[],'observations':[],
                'open_questions':deepcopy(document.get('open_questions',[]))}
        for collection in ('events','states','observations'):
            for index,item in enumerate(document.get(collection,[])):
                value=deepcopy(item)
                for field in ('start_ms','end_ms','video_ms'):
                    if field in value:
                        ms=value[field]
                        if type(ms) is not int or not 0<=ms<=duration or (field=='video_ms' and ms==duration):
                            raise ValueError('history timestamp outside window')
                        value[field]+=window.start_ms
                if 'start_ms' in value and value['start_ms']>=value['end_ms']:raise ValueError('empty history interval')
                local_id=value.get('id',str(index))
                value.update(id=sha256(canonical([key,collection,local_id])).hexdigest()[:24],
                             source_window_id=window.id,request_key=request_key,status='unverified')
                if collection=='events':value['local_event_id']=local_id
                record[collection].append(value)
        self._windows[key]=record

    def gap(self,start_ms,end_ms,reason):
        if (type(start_ms) is not int or type(end_ms) is not int or not 0<=start_ms<end_ms or
            type(reason) is not str or not 0<len(reason)<=160):raise ValueError('invalid gap')
        self._gaps[(start_ms,end_ms,reason)]={'start_ms':start_ms,'end_ms':end_ms,'reason':reason}

    def document(self):
        records=sorted(self._windows.values(),key=lambda r:(r['start_ms'],r['id']))
        return deepcopy({'schema_version':'match-chronology-v1','source_sha256':self.source,
                         'passport':self.passport,'windows':records,
                         **{key:[v for r in records for v in r[key]] for key in ('events','states','observations')},
                         'gaps':sorted(self._gaps.values(),key=lambda g:(g['start_ms'],g['end_ms']))})

    def snapshot(self,before_ms,track_ids=()):
        if type(before_ms) is not int or before_ms<0:raise ValueError('invalid history frontier')
        full=self.document()
        events=sorted((e for e in full['events'] if e['end_ms']<=before_ms),key=lambda e:(e['end_ms'],e['id']))
        states=sorted((s for s in full['states'] if s['end_ms']<=before_ms),key=lambda s:(s['end_ms'],s['id']))
        gaps=[[g['start_ms'],g['end_ms']] for g in full['gaps'] if g['end_ms']<=before_ms]
        gaps.extend([s['start_ms'],s['end_ms']] for s in states if s['kind']=='unknown')
        gaps=merged_intervals(gaps)
        last=states[-1] if states else None
        last_state=None if last is None else {k:last[k] for k in ('id','kind','start_ms','end_ms','status')}
        numbers={}
        for o in full['observations']:
            if o['video_ms']<before_ms and o['track_id'] in track_ids and o.get('number') is not None:
                numbers.setdefault(o['track_id'],set()).add(o['number'])
        hints=[{'track_id':tid,'number':next(iter(values)) if len(values)==1 else None,
                'numbers':sorted(values)[:3],'status':'unverified' if len(values)==1 else 'conflict'}
               for tid,values in sorted(numbers.items())][:8]
        questions=[{'source_window_id':w['source_window_id'],'status':'unverified','question':q}
                   for w in full['windows'] if w['end_ms']<=before_ms for q in w['open_questions']][-4:]
        recent=[{k:e[k] for k in ('id','kind','start_ms','end_ms','team','status')}
                for e in events[-8:]]
        result={'source_sha256':self.source,'confirmed_facts':deepcopy(self.passport['facts']),
                'recent_events':recent,'last_state':last_state,'open_questions':questions,
                'unknown_intervals':gaps[-4:],'number_hints':hints,
                'gap_after_last_state':last is None or before_ms-last['end_ms']>200 or
                    any(end>last['end_ms'] and start<before_ms for start,end in gaps)}
        # Bound the transmitted view; retain every record in document().
        for name in ('recent_events','number_hints','open_questions'):
            while len(canonical(result))>6000 and result[name]:result[name].pop(0)
        if len(canonical(result))>6000:raise ValueError('history snapshot too large')
        return result
