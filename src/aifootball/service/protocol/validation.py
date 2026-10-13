from aifootball.service.errors import DomainError


def validate_confirmation(doc,projection,*,acknowledge_incomplete):
    def invalid(message): raise DomainError('confirmation',message)
    if any(value is None for value in projection.effective_score.values()): invalid('Укажите итоговый счёт обеих команд')
    if doc.result_type=='technical':
        if not doc.technical_reason or not doc.technical_reason.strip(): invalid('Укажите основание технического результата')
    else:
        if doc.completeness.goals=='complete' and projection.effective_score!=projection.event_score:
            invalid('Полный журнал голов не совпадает с итоговым счётом')
        for side in ['home','away']:
            reported=getattr(doc.reported_totals,side)
            for metric,section in [('fouls','fouls'),('yellow_cards','cards'),('dismissals','cards')]:
                value=getattr(reported,metric)
                if getattr(doc.completeness,section)=='complete' and value is not None and value!=projection.event_totals[side][metric]:
                    invalid('Полный журнал не совпадает с командными итогами')
            if reported.period_scores and all(v is not None for v in reported.period_scores.values()):
                if sum(reported.period_scores.values())!=projection.effective_score[side]: invalid('Счёт по таймам не совпадает с общим')
                if doc.completeness.goals=='complete':
                    for period,value in reported.period_scores.items():
                        if value!=projection.period_event_scores.get(period,{'home':0,'away':0})[side]:
                            invalid('Счёт тайма не совпадает с голами')
    if projection.incomplete_sections and not acknowledge_incomplete:
        invalid('Подтвердите, что протокол содержит неполные сведения')
