"""Roster-constrained hints, never assignments. Conflicting numbers are not voted away."""
from collections import defaultdict


def resolve_identity(observations,rosters,*,side_map,track_intervals=None):
    if side_map is not None and (set(side_map)!={'A','B'} or set(side_map.values())!={'home','away'}):
        raise ValueError('Invalid confirmed side map')
    grouped=defaultdict(list)
    for item in observations:grouped[item['track_id']].append(item)
    result=[]
    for track_id,items in sorted(grouped.items()):
        numbers={item['number'] for item in items if item.get('number') is not None}
        teams={item['team'] for item in items if item.get('team') is not None}
        roles={item['role'] for item in items if item.get('role')!='unknown'}
        suggestion={'track_id':track_id,'player_id':None,'status':'unknown','number':next(iter(numbers)) if len(numbers)==1 else None,
                    'team':next(iter(teams)) if len(teams)==1 else None,
                    'evidence_ids':sorted({eid for item in items for eid in item.get('evidence_ids',[])}),'reasons':[]}
        if len(numbers)>1 or len(teams)>1 or ('referee' in roles and len(roles)>1):
            suggestion.update(status='conflict',reasons=['Противоречивые номера/стороны/роли: проверьте смену личности внутри трека'])
        elif not roles or roles=={'referee'}:suggestion['reasons']=['Роль игрока не установлена или наблюдается судья']
        elif not numbers or not teams or side_map is None:suggestion['reasons']=['Нужны читаемый номер и подтверждённое сопоставление сторон']
        else:
            side=side_map[suggestion['team']]
            candidates={person['player_id'] for person in rosters if person['side']==side and person.get('shirt_number')==suggestion['number']}
            if len(candidates)==1:suggestion.update(player_id=next(iter(candidates)),status='candidate',reasons=['Совпадение номера и стороны в снимке состава; требует проверки'])
            elif len(candidates)>1:suggestion.update(status='conflict',reasons=['Дублирующий номер внутри команды'])
            else:suggestion['reasons']=['Номер отсутствует в снимке состава']
        result.append(suggestion)
    if track_intervals is not None:
        conflicts=set()
        for index,first in enumerate(result):
            if first['player_id'] is None:continue
            for second in result[index+1:]:
                if second['player_id']!=first['player_id']:continue
                if any(max(a,c)<min(b,d) for a,b in track_intervals.get(first['track_id'],[]) for c,d in track_intervals.get(second['track_id'],[])):
                    conflicts.update((first['track_id'],second['track_id']))
        for suggestion in result:
            if suggestion['track_id'] in conflicts:suggestion.update(player_id=None,status='conflict',reasons=['Пересекающиеся фрагменты предполагают одного игрока'])
    return result
