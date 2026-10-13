from pydantic import Field
from aifootball.service.tournaments.schemas import Input
from aifootball.service.protocol.events import Goal,Foul,Card,Timeout,ShootoutAttempt,PeriodBoundary,opposite

SIDES=['home','away']


class Projection(Input):
    event_score:dict[str,int]
    effective_score:dict[str,int|None]
    period_event_scores:dict[int,dict[str,int]]
    event_totals:dict[str,dict[str,int]]
    effective_totals:dict[str,dict[str,int|None]]
    reported_totals:dict
    shootout_score:dict[str,int]
    accumulated_fouls:dict[str,dict[str,int]]
    warnings:list[str]
    incomplete_sections:list[str]


def project_protocol(doc,regulation):
    score={s:0 for s in SIDES}; periods={}; shootout={s:0 for s in SIDES}
    totals={s:{'fouls':0,'yellow_cards':0,'dismissals':0} for s in SIDES}
    accumulated={s:{} for s in SIDES}; timeouts={}; warnings=[]
    completeness=doc.completeness.model_dump()
    incomplete={k for k,v in completeness.items() if v!='complete'}
    for e in doc.events:
        if not isinstance(e,(ShootoutAttempt,PeriodBoundary)) and (e.period is None or e.elapsed_ms is None): incomplete.add('time')
        if isinstance(e,Goal):
            side=opposite(e.side) if e.own_goal else e.side
            score[side]+=1
            if e.period is not None:
                periods.setdefault(e.period,{s:0 for s in SIDES})[side]+=1
            if e.player_id is None: incomplete.add('goals')
            if not e.assist_known: incomplete.add('assists')
        elif isinstance(e,Foul):
            totals[e.side]['fouls']+=1
            if e.player_id is None: incomplete.add('fouls')
            if e.accumulated:
                if regulation.fouls.reset=='match': bucket='match'
                elif e.period is None: bucket='unknown'
                elif e.period>len(regulation.periods_s) and regulation.fouls.extra_carry: bucket=str(len(regulation.periods_s))
                else: bucket=str(e.period)
                accumulated[e.side][bucket]=accumulated[e.side].get(bucket,0)+1
        elif isinstance(e,Card):
            if e.card in ['yellow','second_yellow']: totals[e.side]['yellow_cards']+=1
            if e.card in ['red','second_yellow']: totals[e.side]['dismissals']+=1
            if e.player_id is None: incomplete.add('cards')
        elif isinstance(e,ShootoutAttempt) and e.outcome=='goal': shootout[e.side]+=1
        elif isinstance(e,Timeout):
            bucket=(e.side,e.period if regulation.timeouts.scope=='period' else 'match')
            timeouts[bucket]=timeouts.get(bucket,0)+1
            if not regulation.timeouts.allowed or timeouts[bucket]>regulation.timeouts.count:
                warnings.append('Тайм-аут сверх разрешённого лимита; укажите примечание')
    effective={}; effective_totals={s:{} for s in SIDES}
    reported=doc.reported_totals.model_dump(mode='json')
    for side in SIDES:
        effective[side]=reported[side]['score'] if reported[side]['score'] is not None else (score[side] if completeness['goals']=='complete' else None)
        if reported[side]['score'] is not None and reported[side]['score']!=score[side] and doc.result_type!='technical':
            warnings.append(f"{'Хозяева' if side=='home' else 'Гости'}: счёт отличается от известных голов")
        for metric in totals[side]:
            section='fouls' if metric=='fouls' else 'cards'
            value=reported[side][metric]
            effective_totals[side][metric]=value if value is not None else (totals[side][metric] if completeness[section]=='complete' else None)
            if value is not None and value!=totals[side][metric]: warnings.append(f'Итог {metric} отличается от событий команды {side}')
    return Projection(event_score=score,effective_score=effective,period_event_scores=periods,event_totals=totals,
        effective_totals=effective_totals,reported_totals=reported,shootout_score=shootout,accumulated_fouls=accumulated,
        warnings=list(dict.fromkeys(warnings)),incomplete_sections=sorted(incomplete))
