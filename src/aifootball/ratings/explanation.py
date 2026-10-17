"""Small deterministic selection, not an exhaustive account or an LLM verdict."""
from copy import deepcopy

LABELS={'goal':'Гол','pass':'Успешная передача','carry':'Продвижение мяча','recovery':'Возврат контроля','shot_block':'Блок удара',
    'save':'Сейв','distribution':'Точный ввод','turnover':'Потеря мяча','error':'Подтверждённая ошибка','foul':'Фол','card':'Карточка','shot':'Удар'}


def explain_rating(score,facts,actions):
    pid=score.get('player_id');role=score.get('role');public=score.get('scope')=='public'
    positive=[];errors=[]
    ordered=sorted(actions,key=lambda a:(a.get('start_ms') is None,a.get('start_ms') or 0,a['id']))
    for a in ordered:
        if not a.get('verified') or a.get('decision')=='rejected' or a.get('review_status')=='rejected' or a.get('player_id')!=pid or a.get('role') not in (None,role):continue
        own_goal=a['kind']=='goal' and a.get('own_goal',False)
        kind=a['kind'];good=(kind=='goal' and not own_goal) or kind in ('recovery','shot_block') or kind in ('save','distribution','pass','carry','duel') and a.get('success') is True
        bad=own_goal or kind in ('turnover','error','foul','card') or kind in ('pass','distribution','duel') and a.get('success') is False
        if not good and not bad:continue
        evidence=[]
        if not public:
            for ref in a.get('source_refs',[]):
                if ref.get('kind')=='understanding' and ref.get('run_id'):
                    evidence.extend({'run_id':ref['run_id'],'evidence_id':eid} for eid in ref.get('evidence_ids',[]))
        item={'canonical_action_id':a['id'],'role':role,'text':'Автогол' if own_goal else LABELS.get(kind,'Подтверждённое действие') if good else 'Неточная передача' if kind=='pass' else LABELS.get(kind,'Неудачное действие'),
            'start_ms':a.get('start_ms'),'clock_basis':a.get('clock_basis'),'evidence':evidence}
        (positive if good else errors).append(item)
    value=score.get('display_rating');components=score.get('components',{})
    text='Оценка пока недоступна: требуется достаточная база и полный профиль подтверждённых данных.' if score.get('score') is None else f'Пилотная оценка {value:.1f} из 10 рассчитана по подтверждённым показателям роли.'
    note='По автоматическим данным видео: время на площадке и передачи распознаны по записи.' if score.get('source')=='cv_auto' else None
    return {'rating':value,'text':text,'source_note':note,'reasons':list(score.get('reasons',[])),'positive':positive[:3],'errors':errors[:3],
        'components':[{'component_id':key,'value':value} for key,value in sorted(components.items()) if value is not None],
        'selection_is_exhaustive':False,'selection_note':'Это примеры подтверждённых действий. Пустая выборка не означает отсутствия ошибок.'}
