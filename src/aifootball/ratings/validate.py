"""Verified interval arithmetic; no conversion from CV visibility to participation."""
from collections import defaultdict
from aifootball.ratings.schema import ROLES,COMPLETENESS


def intervals(value,duration=86400000):
    if type(value) is not list or len(value)>10000:raise ValueError('Invalid intervals')
    result=[]
    for pair in value:
        if type(pair) not in (list,tuple) or len(pair)!=2 or any(type(v) is not int for v in pair) or not 0<=pair[0]<pair[1]<=duration:
            raise ValueError('Interval outside timeline')
        result.append(list(pair))
    result.sort()
    if any(a[1]>b[0] for a,b in zip(result,result[1:])):raise ValueError('Overlapping intervals')
    return result


def intersection(first,second):
    result=[];i=j=0
    while i<len(first) and j<len(second):
        a,b=first[i],second[j];start=max(a[0],b[0]);end=min(a[1],b[1])
        if start<end:result.append([start,end])
        if a[1]<=b[1]:i+=1
        else:j+=1
    return result


def duration_s(items):return sum(b-a for a,b in items)/1000


def _remaining(presence,roles):
    result=[]
    for start,end in presence:
        cursor=start
        for a,b in roles:
            if b<=cursor:continue
            if a>=end:break
            if cursor<a:result.append([cursor,min(a,end)])
            cursor=max(cursor,b)
            if cursor>=end:break
        if cursor<end:result.append([cursor,end])
    return result


def exposure_by_role(participation,play_intervals,possession_intervals):
    presence=participation.get('presence');complete=participation.get('completeness','complete')=='complete'
    if presence is None:return {'unknown':{'on_pitch_s':None,'known_on_pitch_s':0,'effective_play_s':None,'eligible_play_s':None,'possession_s':None,'without_possession_s':None}}
    presence=intervals(presence);roles=defaultdict(list)
    for role in participation.get('roles',[]):roles[role['role']].extend(intervals(role['intervals']))
    known=intervals([pair for values in roles.values() for pair in values])
    remaining=_remaining(presence,known)
    if remaining:roles['unknown'].extend(remaining)
    if not roles:roles['unknown']=[]
    play=presence if participation.get('time_basis')=='official_clean' else None if play_intervals is None else intervals(play_intervals)
    possession=None if possession_intervals is None else intervals(possession_intervals)
    opponent=participation.get('opponent_possession_intervals')
    opponent=None if opponent is None else intervals(opponent)
    result={}
    for role,ranges in roles.items():
        ranges=intersection(presence,intervals(ranges));on_pitch=duration_s(ranges)
        effective_ranges=intersection(ranges,play) if play is not None else None
        effective=None if not complete or effective_ranges is None else duration_s(effective_ranges)
        result[role]={'on_pitch_s':on_pitch if complete else None,'known_on_pitch_s':on_pitch,'effective_play_s':effective,
            'eligible_play_s':(on_pitch if complete else None) if participation.get('time_basis')=='running_clock' else effective,
            'possession_s':duration_s(intersection(effective_ranges,possession)) if complete and effective_ranges is not None and possession is not None else None,
            'without_possession_s':duration_s(intersection(effective_ranges,opponent)) if complete and effective_ranges is not None and opponent is not None else None}
    return result


def _capacity(ranges,limit,overrides,duration,label):
    deltas=defaultdict(int)
    for a,b in ranges:deltas[a]+=1;deltas[b]-=1
    for item in overrides:deltas[item['start_ms']]+=0;deltas[item['end_ms']]+=0
    count=0
    for time,delta in sorted(deltas.items()):
        count+=delta
        allowed=next((item['max_players'] for item in overrides if item['start_ms']<=time<item['end_ms']),limit)
        if time<duration and count>allowed:raise ValueError(label+' capacity exceeded')


def validate_participation(document,roster,*,players_on_pitch):
    duration=document['duration_ms'];known={p['player_id']:p['side'] for p in roster};seen=set()
    if type(duration) is not int or not 0<duration<=86400000:raise ValueError('Invalid timeline duration')
    for side in ('home','away'):
        initial=document['initial_five'].get(side,[])
        if len(initial)!=len(set(initial)) or len(initial)>players_on_pitch or any(known.get(pid)!=side for pid in initial):
            raise ValueError('Invalid initial five')
    if document.get('play_intervals') is not None:intervals(document['play_intervals'],duration)
    possession=document.get('possession_intervals',{'home':None,'away':None})
    for side in ('home','away'):
        if possession.get(side) is not None:intervals(possession[side],duration)
    if all(possession.get(side) is not None for side in ('home','away')):
        if intersection(intervals(possession['home']),intervals(possession['away'])):raise ValueError('Overlapping team possession')
    manpower=document.get('manpower',[])
    for side in ('home','away'):
        entries=[v for v in manpower if v['side']==side]
        intervals([[v['start_ms'],v['end_ms']] for v in entries],duration)
        if any(type(v['max_players']) is not int or not 1<=v['max_players']<=players_on_pitch or not v.get('reason','').strip() for v in entries):
            raise ValueError('Invalid manpower limit')
    presence_by_side=defaultdict(list);keepers=defaultdict(list)
    for player in document['players']:
        pid=player['player_id']
        if pid not in known or pid in seen:raise ValueError('Unknown/duplicate roster player')
        seen.add(pid);presence=player.get('presence');completeness=player.get('completeness','unknown')
        if completeness not in COMPLETENESS or (presence is None and completeness=='complete'):raise ValueError('Unknown presence cannot be complete')
        if presence is not None:
            presence=intervals(presence,duration);presence_by_side[known[pid]].extend(presence)
            if player.get('appeared') is False and presence:raise ValueError('Presence contradicts non-appearance')
        role_ranges=[];role_names=set()
        for role in player.get('roles',[]):
            if role['role'] not in ROLES or role['role'] in role_names:raise ValueError('Invalid/duplicate role')
            role_names.add(role['role']);ranges=intervals(role['intervals'],duration)
            if presence is None or duration_s(intersection(presence,ranges))!=duration_s(ranges):raise ValueError('Role outside presence')
            role_ranges.extend(ranges)
            if role['role']=='goalkeeper':keepers[known[pid]].extend(ranges)
        try:intervals(role_ranges,duration)
        except ValueError as exc:raise ValueError('Overlapping role intervals') from exc
    for side in ('home','away'):
        _capacity(presence_by_side[side],players_on_pitch,[v for v in manpower if v['side']==side],duration,'Player')
        _capacity(keepers[side],1,[],duration,'Goalkeeper role')
    return document
