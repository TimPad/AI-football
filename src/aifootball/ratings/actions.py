"""Canonical facts: explicit links, official authors, no inferred completeness."""
from copy import deepcopy

MANUAL_KINDS={'shot','pass','carry','duel','recovery','shot_block','turnover','save','distribution','error','goal_candidate'}
OFFICIAL_KINDS={'goal','foul','card','penalty_awarded','penalty_attempt'}
FIELDS={'id','kind','player_id','recipient_id','opponent_id','side','role','start_ms','end_ms','clock_basis',
    'success','on_target','outcome','possession_id','start_xy','end_xy','attacking_direction','period','elapsed_ms','video_ms',
    'assist_id','assist_known','own_goal','from_penalty','penalty_id','card','previous_yellow_id','penalty_conceded',
    'source_episode_id','shot_id'}


def _refs(record,kind):return deepcopy(record.get('source_refs') or [{'kind':kind,'id':record['id']}])


def _record(record,kind,protocol):
    value={key:deepcopy(v) for key,v in record.items() if key in FIELDS}
    value.setdefault('player_id',None);value.setdefault('side',None)
    value.setdefault('clock_basis',protocol.get('clock_basis','game'))
    if value.get('start_ms') is None:
        if value['clock_basis']=='video':value['start_ms']=record.get('video_ms')
        elif record.get('period') is not None and record.get('elapsed_ms') is not None:
            offset=protocol.get('period_offsets_ms',{}).get(str(record['period']))
            value['start_ms']=offset+record['elapsed_ms'] if offset is not None else None
        else:value['start_ms']=None
    value.setdefault('end_ms',value['start_ms']);value['source_refs']=_refs(record,kind)
    value['canonical_event_id']=value['id'];value['incident_id']=value['id']
    value['source_kind']=kind;value['verified']=True
    value['counts_as_player_goal']=value['kind']=='goal' and not value.get('own_goal',False)
    value['non_penalty_goal']=value['counts_as_player_goal'] and not value.get('from_penalty',False)
    value['counts_as_shot']=value['kind']=='shot' or value['counts_as_player_goal']
    if value['kind']=='goal':
        value['assist_id']=record.get('assist_id') if record.get('assist_known') and not record.get('own_goal') else None
        value['on_target']=True if value['counts_as_shot'] else None
    return value


def _same_context(target,source,*,manual_pair=False):
    for key in ('player_id','side'):
        if target.get(key) is not None and source.get(key) is not None and target[key]!=source[key]:
            raise ValueError('Canonical link has conflicting '+key)
    first,second=target.get('start_ms'),source.get('start_ms')
    if manual_pair and (first is None or second is None):raise ValueError('Manual deduplication requires source times')
    if first is not None and second is not None:
        if target.get('clock_basis')!=source.get('clock_basis'):raise ValueError('Clock mapping required for canonical link')
        if abs(first-second)>2000:raise ValueError('Canonical events are separated in time')


def canonical_actions(protocol:dict,reviewed_actions:list[dict],links:list[dict])->list[dict]:
    events=protocol.get('events',[])
    if len(events)>10000 or len(reviewed_actions)>10000 or len(links)>20000:raise ValueError('Action limit exceeded')
    ids=[item['id'] for item in [*events,*reviewed_actions]]
    if any(type(v) is not str or not v for v in ids) or len(set(ids))!=len(ids):raise ValueError('Duplicate/invalid source event ID')
    official={e['id'] for e in events};records={};penalty_goals={}
    for event in events:
        if event['kind']=='goal' and event.get('from_penalty'):
            pid=event.get('penalty_id')
            if pid is None or pid in penalty_goals:raise ValueError('Invalid penalty-goal linkage')
            penalty_goals[pid]=event['id']
    for event in events:
        if event['kind'] not in OFFICIAL_KINDS or event['kind']=='penalty_attempt':continue
        records[event['id']]=_record(event,'protocol',protocol)
    for event in events:
        if event['kind']!='penalty_attempt':continue
        if event.get('outcome')=='goal':
            target=records.get(penalty_goals.get(event.get('penalty_id')))
            if target is None:raise ValueError('Successful penalty requires one official goal')
            _same_context(target,_record(event,'protocol',protocol))
            target['source_refs'].extend(_refs(event,'protocol'))
        else:
            shot=_record({**event,'kind':'shot','from_penalty':True,
                'on_target':True if event.get('outcome')=='saved' else False if event.get('outcome')=='off_target' else None},'protocol',protocol)
            records[event['id']]=shot
    for action in reviewed_actions:
        if action.get('decision')=='rejected' or action.get('review_status')=='rejected':continue
        if type(action['kind']) is not str or action['kind'] not in MANUAL_KINDS:raise ValueError('Official fact must come from protocol')
        records[action['id']]=_record(action,'reviewed_video' if action.get('source_episode_id') else 'manual',protocol)
    canonical_links=[link for link in links if link.get('kind','canonical')=='canonical']
    sources=[link['source_event_id'] for link in canonical_links]
    targets={link['canonical_event_id'] for link in canonical_links}
    if len(sources)!=len(set(sources)) or set(sources)&targets:raise ValueError('Ambiguous/cyclic canonical links')
    for link in canonical_links:
        tid,sid=link['canonical_event_id'],link['source_event_id']
        if tid==sid or tid not in records or sid not in records or sid in official:raise ValueError('Invalid canonical link')
        target,source=records[tid],records[sid]
        compatible=(target['kind']=='goal' and source['kind'] in ('goal_candidate','shot')) or target['kind']==source['kind']
        if not compatible:raise ValueError('Different action kinds cannot be deduplicated')
        if target['kind']=='goal' and source['kind']=='shot' and source.get('outcome')!='goal':raise ValueError('Linked shot must be the goal attempt')
        _same_context(target,source,manual_pair=tid not in official)
        if tid not in official:
            for key in ('success','on_target','outcome','recipient_id','opponent_id'):
                if target.get(key) is not None and source.get(key) is not None and target[key]!=source[key]:raise ValueError('Conflicting duplicate action')
        target['source_refs'].extend(source['source_refs'])
        for key in ('start_ms','end_ms','role','start_xy','end_xy','possession_id','attacking_direction','shot_id'):
            if target.get(key) is None and source.get(key) is not None:target[key]=deepcopy(source[key])
        if target.get('start_ms') is not None and source.get('start_ms')==target['start_ms']:target['clock_basis']=source['clock_basis']
        del records[sid]
    if any(r['kind']=='shot' and r.get('outcome')=='goal' for r in records.values()):
        raise ValueError('Goal attempt must link to one official goal before counting shots')
    incident_pairs=set()
    for link in links:
        if link.get('kind','canonical')=='canonical':continue
        if link.get('kind')!='incident':raise ValueError('Unknown link kind')
        tid,sid=link['canonical_event_id'],link['source_event_id']
        if tid==sid or tid not in records or sid not in records or (tid,sid) in incident_pairs:raise ValueError('Invalid incident link')
        incident_pairs.add((tid,sid));target,source=records[tid],records[sid]
        allowed={'foul','card','penalty_awarded','error'}
        if target['kind'] not in allowed or source['kind'] not in allowed:raise ValueError('Unrelated incident actions')
        if target.get('previous_yellow_id')==sid or source.get('previous_yellow_id')==tid:raise ValueError('First yellow remains a separate incident')
        if 'penalty_awarded' not in (target['kind'],source['kind']):_same_context(target,source)
        else:
            if target.get('start_ms') is not None and source.get('start_ms') is not None and abs(target['start_ms']-source['start_ms'])>2000:raise ValueError('Unrelated penalty incident')
        old=source['incident_id'];new=target['incident_id']
        for record in records.values():
            if record['incident_id']==old:record['incident_id']=new
    return sorted((r for r in records.values() if r['kind']!='goal_candidate'),key=lambda r:(r.get('start_ms') is None,r.get('start_ms') or 0,r['id']))


def discipline_cost(actions,player_id):
    incidents={}
    for action in actions:
        if action.get('player_id')!=player_id:continue
        cost=1 if action['kind']=='foul' else (2 if action.get('card')=='yellow' else 5) if action['kind']=='card' else 3 if action['kind']=='error' and action.get('penalty_conceded') else 0
        key=action.get('incident_id',action['id']);incidents[key]=max(incidents.get(key,0),cost)
    return sum(incidents.values())
