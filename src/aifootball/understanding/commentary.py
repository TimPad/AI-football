"""Deterministic, video-timed preview from unverified structured observations."""
from hashlib import sha256

from aifootball.analytics.exchange import canonical
from aifootball.understanding.context_pilot import event_eligibility,state_supported
from aifootball.understanding.match_context import validate_passport

POLICY='observed-commentary-v1'
TEMPLATES={
    'shot_candidate':'Возможный удар в сторону ворот.',
    'save_candidate':'Вратарь отражает мяч после удара.',
    'goal_candidate':'Возможный гол: мяч виден в сетке. Эпизод требует проверки.',
    'kick_in':'Мяч вводится в игру из-за боковой линии.',
    'corner':'Возможный угловой: мяч возвращается в игру у угла площадки.',
    'kickoff':'Розыгрыш мяча с центра площадки.',
    'free_kick_candidate':'Возобновление игры после сигнала судьи.',
    'pressing_candidate':'Игроки сближаются с соперником, владеющим мячом.',
    'substitution_candidate':'Возможная замена игроков.',
}
COLORS={'зелёная':'Зелёные','оранжевая':'Оранжевые','розовая':'Розовые','зелёно-белая':'Зелёно-белые'}


def compile_commentary(chronology,passport):
    passport=validate_passport(passport,chronology['source_sha256'])
    entries=[];rejected=[];highlights=[];source=chronology['source_sha256']
    def append(item,text,kind):
        entries.append({'id':sha256(canonical([source,POLICY,kind,item['id']])).hexdigest()[:24],
                        'video_ms':item['start_ms'],'start_ms':item['start_ms'],'end_ms':item['end_ms'],
                        'timestamp_basis':'video','clock_ms':None,'text':text,'source_id':item['id'],
                        'source_window_id':item['source_window_id'],'evidence_ids':item['evidence_ids'],
                        'status':'unverified'})
    for event in chronology['events']:
        eligible,reason=event_eligibility(event)
        if not eligible:
            rejected.append({'event_id':event['id'],'kind':event['kind'],'reason':reason,
                             'visual_signals':event.get('visual_signals',[])})
            continue
        text=TEMPLATES[event['kind']]
        side=event.get('team');color=passport['facts'].get(f'team_{side}_color')
        if color and event['kind'] not in ('save_candidate','goal_candidate'):
            label=COLORS.get(color['value'],f'Команда {side}')
            text=label+': '+text[0].lower()+text[1:]
        append(event,text,'event')
        if event['kind'] in ('shot_candidate','save_candidate','goal_candidate'):
            highlights.append({'event_id':event['id'],'start_ms':event['start_ms'],'end_ms':event['end_ms'],
                               'status':'unverified'})
    previous=None
    for state in sorted(chronology['states'],key=lambda s:(s['start_ms'],s['end_ms'],s['id'])):
        if state['kind'] in ('playing','stoppage') and not state_supported(state):state={**state,'kind':'unknown'}
        contiguous=previous is not None and 0<=state['start_ms']-previous['end_ms']<=200 and not any(
            g['start_ms']<=state['start_ms'] and g['end_ms']>=previous['end_ms'] for g in chronology['gaps'])
        if state['kind']=='stoppage' and (previous is None or previous['kind']!='stoppage' or not contiguous):
            append(state,'Наблюдается остановка игры.','state')
        if state['kind']=='playing' and contiguous and previous['kind']=='stoppage':
            append(state,'Игра возобновилась.','state')
        previous=state
    entries=sorted({e['id']:e for e in entries}.values(),key=lambda e:(e['video_ms'],e['id']))
    return {'schema_version':POLICY,'source_sha256':source,'entries':entries,
            'rejected_events':rejected,'highlight_candidates':highlights}
