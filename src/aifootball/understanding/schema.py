"""Pure, bounded schema validation. No model, network or service dependencies."""
from copy import deepcopy
from hashlib import sha256
import json
import math
import re
from uuid import UUID

STATE_KINDS={'pre_match','playing','stoppage','break','post_match','unknown'}
PHASE_KINDS={'attack','defend','transition','unknown'}
EVENT_KINDS={'kickoff','kick_in','corner','free_kick_candidate','penalty_candidate','timeout',
             'shot_candidate','save_candidate','goal_candidate','substitution_candidate',
             'keeper_out_candidate','pressing_candidate','compact_block_candidate','unknown'}
ROLES={'player','goalkeeper','referee','unknown'}
SCOPES={'full_match','continuous_excerpt','highlights','unknown'}
METRICS={'observed_s','distance_m','m_per_min','hsr_m','sprints','vmax_ms','width_m','depth_m','compactness_m2'}
MAX_JSON=8*1024*1024


def require(condition,label):
    if not condition:raise ValueError(f'Invalid understanding: {label}')


def fields(value,required,optional=()):
    require(type(value) is dict,'object')
    wanted=set(required.split()) if isinstance(required,str) else set(required)
    allowed=set(optional.split()) if isinstance(optional,str) else set(optional)
    require(wanted<=value.keys() and value.keys()<=wanted|allowed,'fields')


def integer(value,label,minimum=0,maximum=2**31-1):
    require(type(value) is int and minimum<=value<=maximum,label)
    return value


def string(value,label,maximum=10000,empty=True):
    require(type(value) is str and len(value)<=maximum and (empty or bool(value.strip())),label)


def identifier(value,label):
    require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',value),label)


def hash_value(value,label):
    require(type(value) is str and re.fullmatch(r'[a-f0-9]{64}',value),label)


def uuid_value(value):
    try:require(type(value) is str and str(UUID(value))==value,'UUID')
    except (ValueError,AttributeError,TypeError):raise ValueError('Invalid understanding: UUID') from None


def bounded_list(value,label,maximum=10000):
    require(type(value) is list and len(value)<=maximum,label)
    return value


def finite(value,depth=0):
    require(depth<=32,'depth')
    if type(value) is dict:
        for key,item in value.items():string(key,'key',500);finite(item,depth+1)
    elif type(value) is list:
        require(len(value)<=100000,'list size')
        for item in value:finite(item,depth+1)
    elif type(value) is str:string(value,'text')
    elif type(value) is float:require(math.isfinite(value),'finite numbers')
    else:require(value is None or type(value) in (bool,int),'JSON type')


def interval(value,duration):
    integer(value['start_ms'],'start_ms',maximum=duration)
    integer(value['end_ms'],'end_ms',maximum=duration)
    require(value['start_ms']<value['end_ms'],'interval')


def refs(value,known,label):
    bounded_list(value,label,1000)
    require(all(type(item) is str and item in known for item in value),'unknown '+label)
    require(len(value)==len(set(value)),'duplicate '+label)


def notes(value):
    for note in bounded_list(value,'limitations',100):string(note,'limitation',1000)


def validate_items(document,*,duration,track_ids,evidence_ids,media=None):
    events={}
    for item in bounded_list(document['observations'],'observations'):
        fields(item,'track_id video_ms role number team evidence_ids visible_features limitations')
        integer(item['track_id'],'track_id');require(item['track_id'] in track_ids,'unknown track')
        integer(item['video_ms'],'video_ms',maximum=duration-1)
        require(type(item['role']) is str and item['role'] in ROLES,'role');require(item['team'] in ('A','B',None),'team')
        require(item['number'] is None or (type(item['number']) is str and re.fullmatch(r'[0-9]{1,3}',item['number'])),'number')
        refs(item['evidence_ids'],evidence_ids,'evidence');notes(item['limitations'])
        if item['number'] is not None:require(bool(item['evidence_ids']),'number evidence')
        for feature in bounded_list(item['visible_features'],'visible_features',20):string(feature,'feature',500)
    for kind in ('states','phases'):
        for item in bounded_list(document[kind],kind):
            fields(item,'kind start_ms end_ms evidence_ids limitations' if kind=='states' else
                   'kind team possession attacking_direction start_ms end_ms evidence_ids limitations')
            interval(item,duration);refs(item['evidence_ids'],evidence_ids,'evidence');notes(item['limitations'])
            require(type(item['kind']) is str and item['kind'] in (STATE_KINDS if kind=='states' else PHASE_KINDS),'kind')
            if kind=='phases':
                require(item['team'] in ('A','B',None) and item['possession'] in ('A','B',None),'phase team')
                require(item['attacking_direction'] in ('left','right','unknown'),'direction')
    for item in bounded_list(document['events'],'events'):
        fields(item,'id kind start_ms end_ms team track_ids evidence_ids audio_observations limitations')
        identifier(item['id'],'event id');require(item['id'] not in events,'duplicate event')
        events[item['id']]=item
        require(type(item['kind']) is str and item['kind'] in EVENT_KINDS,'event kind');require(item['team'] in ('A','B',None),'event team')
        interval(item,duration);refs(item['evidence_ids'],evidence_ids,'evidence');notes(item['limitations'])
        ids=bounded_list(item['track_ids'],'track_ids',100)
        require(all(type(tid) is int and tid in track_ids for tid in ids) and len(set(ids))==len(ids),'unknown/duplicate track')
        for audio in bounded_list(item['audio_observations'],'audio',20):
            fields(audio,'kind text start_ms end_ms clip_sha256')
            interval(audio,duration);hash_value(audio['clip_sha256'],'clip hash')
            require(audio['kind'] in ('whistle','commentary','reaction','unknown'),'audio kind')
            if audio['text'] is not None:string(audio['text'],'audio text',1000)
            if media is not None:require(media.has_audio and audio['clip_sha256']==media.sha256,'audio clip')
    for item in bounded_list(document['summary'],'summary',1000):
        fields(item,'text event_ids metric_refs');string(item['text'],'summary text',empty=False)
        refs(item['event_ids'],set(events),'event')
        require(bool(item['event_ids'] or item['metric_refs']),'unreferenced summary')
        for ref in bounded_list(item['metric_refs'],'metric refs',100):
            fields(ref,'period_key metric_name','team track_id');string(ref['period_key'],'period',50,False)
            require(('team' in ref)^('track_id' in ref),'metric owner')
            require(type(ref['metric_name']) is str and ref['metric_name'] in METRICS,'metric name')
            if 'team' in ref:require(ref['team'] in ('A','B'),'metric team')
            else:require(type(ref['track_id']) is int and ref['track_id'] in track_ids,'metric track')


def restrict_to_tracks(document,track_ids):
    """Keep only references to packaged tracks; windows may see short tracks the package drops."""
    out=deepcopy(document);dropped=0
    def keep(tid):
        nonlocal dropped
        if tid in track_ids:return True
        dropped+=1;return False
    out['observations']=[o for o in out['observations'] if keep(o['track_id'])]
    out['identity_suggestions']=[s for s in out['identity_suggestions'] if keep(s['track_id'])]
    for item in out['events']:item['track_ids']=[tid for tid in item['track_ids'] if keep(tid)]
    summary=[]
    for item in out['summary']:
        item['metric_refs']=[r for r in item['metric_refs'] if 'track_id' not in r or keep(r['track_id'])]
        if item['event_ids'] or item['metric_refs']:summary.append(item)
    out['summary']=summary
    if dropped:
        used={eid for kind in ('observations','identity_suggestions','states','phases','events') for item in out[kind] for eid in item['evidence_ids']}
        out['evidence']=[item for item in out['evidence'] if item['id'] in used]
    if dropped and 'processing' in out:
        processing=out['processing']
        processing['issues']=[*processing['issues'],f'Ссылки на короткие треки без интервалов в пакете не сохранены: {dropped}']
        processing['status']='partial' if processing['tasks_completed'] else 'unavailable'
    return out


def validate_understanding(document,*,manifest,tracks,files=None,rosters=None):
    fields(document,'schema_version source context provider budget coverage evidence observations identity_suggestions states phases events summary','processing')
    finite(document)
    require(document['schema_version']=='1','schema version')
    require(len(json.dumps(document,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode())<=MAX_JSON,'JSON size')
    source=document['source'];fields(source,'sha256 duration_ms width height','analysis_scope')
    hash_value(source['sha256'],'source hash')
    require(source['sha256']==manifest['source_video']['sha256'],'source hash mismatch')
    duration=integer(source['duration_ms'],'duration_ms',minimum=1,maximum=86400000)
    require(duration==round(manifest['source_video']['duration_s']*1000),'duration mismatch')
    for key in ('width','height'):
        integer(source[key],key,1,32768);require(source[key]==manifest['source_video'][key],'dimension mismatch')
    require(type(source.get('analysis_scope','unknown')) is str and source.get('analysis_scope','unknown') in SCOPES,'analysis_scope')
    context=document['context'];fields(context,'job_id match_id context_hash camera_profile_id')
    for key in context:
        (hash_value(context[key],key) if key=='context_hash' else uuid_value(context[key]))
        require(context[key]==manifest[key],'context mismatch')
    provider=document['provider'];fields(provider,'name model response_model endpoint region prompt_version settings')
    require(provider['name']=='qwen','provider')
    for key in ('model','prompt_version'):string(provider[key],key,200,False)
    for key in ('response_model','endpoint','region'):
        if provider[key] is not None:string(provider[key],key,500)
    fields(provider['settings'],'','mode reasoning_effort fps max_images max_body_bytes max_clip_ms')
    settings=provider['settings']
    if 'mode' in settings:require(settings['mode'] in ('native','frames'),'mode')
    if 'reasoning_effort' in settings:require(settings['reasoning_effort']=='none','reasoning_effort')
    for key in ('fps','max_images','max_body_bytes','max_clip_ms'):
        if key in settings:integer(settings[key],key,1,128*1024*1024)
    budget=document['budget'];fields(budget,'max_requests max_input_tokens max_output_tokens requests input_tokens output_tokens usage_unknown')
    for key in budget:
        if key=='usage_unknown':require(type(budget[key]) is bool,'usage_unknown')
        else:integer(budget[key],key,0,10**12)
    # Actual usage can exceed a pre-request estimate. Preserve it and stop future calls.
    require(budget['requests']<=budget['max_requests'],'request budget exceeded')
    coverage=document['coverage'];fields(coverage,'covered_intervals unknown_intervals status')
    ranges=[]
    for kind in ('covered_intervals','unknown_intervals'):
        for pair in bounded_list(coverage[kind],kind,10000):
            require(type(pair) is list and len(pair)==2,'coverage interval')
            integer(pair[0],'coverage start',maximum=duration);integer(pair[1],'coverage end',maximum=duration)
            require(pair[0]<pair[1],'coverage interval');ranges.append(pair)
    cursor=0
    for start,end in sorted(ranges):require(start==cursor,'coverage partition');cursor=end
    require(cursor==duration,'coverage partition')
    expected='unavailable' if not coverage['covered_intervals'] else 'partial' if coverage['unknown_intervals'] else 'complete'
    require(coverage['status']==expected,'coverage status')
    if 'processing' in document:
        processing=document['processing']
        fields(processing,'status tasks_planned tasks_completed scene_tasks_planned scene_tasks_completed identity_tasks_planned identity_tasks_completed issues')
        for key in ('tasks_planned','tasks_completed','scene_tasks_planned','scene_tasks_completed','identity_tasks_planned','identity_tasks_completed'):
            integer(processing[key],key,0,100000)
        notes(processing['issues'])
        for stage in ('scene','identity'):
            require(processing[f'{stage}_tasks_completed']<=processing[f'{stage}_tasks_planned'],'stage count')
        for kind in ('planned','completed'):
            require(processing[f'tasks_{kind}']==processing[f'scene_tasks_{kind}']+processing[f'identity_tasks_{kind}'],'task count')
        status='unavailable' if not processing['tasks_completed'] else 'complete' if processing['tasks_completed']==processing['tasks_planned'] and not processing['issues'] else 'partial'
        require(processing['status']==status,'processing status')
    evidence_ids=set();paths=set()
    for item in bounded_list(document['evidence'],'evidence',500):
        fields(item,'id frame_id video_ms path sha256 crop kind')
        identifier(item['id'],'evidence id');require(item['id'] not in evidence_ids,'duplicate evidence');evidence_ids.add(item['id'])
        integer(item['frame_id'],'frame_id');integer(item['video_ms'],'evidence time',maximum=duration-1)
        require(type(item['path']) is str and re.fullmatch(r'evidence/[A-Za-z0-9_-]{1,100}\.jpg',item['path']) and item['path'] not in paths,'evidence path');paths.add(item['path'])
        require(item['kind'] in ('overview','player_crop'),'evidence kind');hash_value(item['sha256'],'evidence hash')
        if item['crop'] is not None:
            crop=item['crop'];require(type(crop) is list and len(crop)==4,'crop')
            for value in crop:integer(value,'crop coordinate',maximum=32768)
            require(0<=crop[0]<crop[2]<=source['width'] and 0<=crop[1]<crop[3]<=source['height'],'crop bounds')
        if files is not None:
            require(item['path'] in files,'missing evidence');raw=files[item['path']]
            require(type(raw) is bytes and len(raw)<=512*1024,'evidence size')
            require(sha256(raw).hexdigest()==item['sha256'],'evidence hash mismatch')
    track_ids={item['track_id'] for item in tracks['tracks']}
    validate_items(document,duration=duration,track_ids=track_ids,evidence_ids=evidence_ids)
    roster_ids={item['player_id'] for item in rosters} if rosters is not None else None
    seen=set()
    for item in bounded_list(document['identity_suggestions'],'identity_suggestions'):
        fields(item,'track_id player_id status number team evidence_ids reasons')
        require(type(item['track_id']) is int and item['track_id'] in track_ids and item['track_id'] not in seen,'identity track');seen.add(item['track_id'])
        require(item['status'] in ('candidate','conflict','unknown'),'identity status')
        require(item['team'] in ('A','B',None),'identity team')
        require(item['number'] is None or (type(item['number']) is str and re.fullmatch(r'[0-9]{1,3}',item['number'])),'identity number')
        refs(item['evidence_ids'],evidence_ids,'evidence');notes(item['reasons'])
        if item['player_id'] is not None:
            uuid_value(item['player_id']);require(item['status']=='candidate','identity status')
            if roster_ids is not None:require(item['player_id'] in roster_ids,'identity roster')
            require(item['number'] is not None and item['team'] is not None and bool(item['evidence_ids']),'identity evidence')
    out=deepcopy(document);out['source'].setdefault('analysis_scope','unknown');return out


def to_window_time(document,window):
    """Convert times that are impossible as window-relative but exact as source-absolute."""
    out=deepcopy(document);start,end=window.start_ms,window.end_ms;duration=end-start
    def absolute(value,limit):return type(value) is int and value>limit and start<=value<=end
    for item in out.get('observations') or []:
        if isinstance(item,dict) and absolute(item.get('video_ms'),duration-1)and item['video_ms']<end:item['video_ms']-=start
    def interval(item):
        if isinstance(item,dict) and absolute(item.get('start_ms'),-1) and absolute(item.get('end_ms'),duration) and start>0:
            item['start_ms']-=start;item['end_ms']-=start
    for kind in ('events','states','phases'):
        for item in out.get(kind) or []:
            interval(item)
            for audio in (item.get('audio_observations') or []) if isinstance(item,dict) else []:interval(audio)
    # Текст сводки без ссылок на события или метрики не подтверждён — отбрасывается, наблюдения окна остаются.
    if isinstance(out.get('summary'),list):
        out['summary']=[item for item in out['summary'] if not isinstance(item,dict) or item.get('event_ids') or item.get('metric_refs')]
    return out


def validate_window_response(document,window):
    fields(document,'time_basis observations states phases events summary');finite(document)
    document=to_window_time(document,window)
    require(document['time_basis']=='window','time basis')
    require(type(window.start_ms) is int and type(window.end_ms) is int and 0<=window.start_ms<window.end_ms,'window bounds')
    duration=window.end_ms-window.start_ms
    require(duration<=20000,'window length')
    require(len(window.frames)<=32,'frame count')
    known={frame.id for frame in window.frames};require(len(known)==len(window.frames),'duplicate frame')
    for frame in window.frames:
        require(window.start_ms<=frame.video_ms<window.end_ms,'frame window bounds');hash_value(frame.sha256,'frame hash')
    if window.media is not None:
        require(window.media.start_ms==window.start_ms and window.media.end_ms==window.end_ms,'clip source bounds')
    validate_items(document,duration=duration,track_ids=set(window.track_ids),evidence_ids=known,media=window.media)
    if window.media is None:require(all(not event['audio_observations'] for event in document['events']),'audio without clip')
    out=deepcopy(document);out['time_basis']='video'
    for kind in ('events','states','phases'):
        for item in out[kind]:
            item['start_ms']+=window.start_ms;item['end_ms']+=window.start_ms
            if kind=='events':
                for audio in item['audio_observations']:audio['start_ms']+=window.start_ms;audio['end_ms']+=window.start_ms
    for item in out['observations']:item['video_ms']+=window.start_ms
    return {'window_id':window.id,'start_ms':window.start_ms,'end_ms':window.end_ms,'document':out,'evidence':[]}
