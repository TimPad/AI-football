"""Командная сводка действий матча по одной версии: только сохранённые канонические факты.

Полнота категории берётся из объявления версии и не выводится из числа записей.
Неизвестный исход остаётся отдельным числом и не входит в знаменатель процента.
"""
from sqlalchemy import select
from aifootball.service.errors import DomainError
from aifootball.service.ratings.models import ActionVersion,RatingMatchPublication

SIDES=('home','away')
# (ключ, подпись, группа, категория полноты, вид значения)
ROWS=[
    ('shots_total','Всего ударов','shots','shots','count'),
    ('shots_on_target','Удары в створ','shots','shots','count'),
    ('shots_off_target','Удары мимо ворот','shots','shots','count'),
    ('shots_blocked','Заблокированные удары','shots','shots','count'),
    ('passes_total','Передачи','passes','passes','count'),
    ('passes_accurate','Точные передачи','passes','passes','percent'),
    ('carries_successful','Удачные ведения','passes','carries','percent'),
    ('duels_won','Выигранные единоборства','defense','duels','percent'),
    ('recoveries','Возвраты мяча','defense','recoveries','count'),
    ('shot_blocks','Блокировки ударов','defense','shot_blocks','count'),
    ('turnovers','Потери','defense','turnovers','count'),
    ('saves','Сейвы','goalkeeping','saves','count'),
    ('distribution_accurate','Точные вводы вратаря','goalkeeping','distribution','percent'),
    ('errors','Ошибки','defense','errors','count'),
]


def _coverage(doc,category):
    items=(doc.get('completeness') or {}).get(category) or []
    full=[[0,doc['duration_ms']]]
    if any(i['status']=='complete' and i.get('player_ids') is None and (i.get('intervals') is None or i['intervals']==full) for i in items):
        return 'complete'
    return 'partial' if any(i['status'] in ('complete','partial') for i in items) else 'unknown'


def _periods(version):
    if version.document.get('clock_basis')!='game':return []
    rules=(version.provenance or {}).get('regulation') or {}
    regular=list(rules.get('periods_s') or []);extra=rules.get('extra') or {}
    extra_periods=list(extra.get('periods_s') or []) if extra.get('enabled') else []
    bounds=[];cursor=0
    for index,seconds in enumerate(regular+extra_periods,1):
        label=f'{index}-й тайм' if index<=len(regular) else f'Доп. время {index-len(regular)}'
        bounds.append({'key':str(index),'label':label,'start_ms':cursor,'end_ms':cursor+seconds*1000});cursor+=seconds*1000
    return bounds


def _period_of(record,bounds):
    if record.get('period') is not None:return str(record['period'])
    start=record.get('start_ms')
    if start is None or record.get('clock_basis','game')!='game':return None
    return next((b['key'] for b in bounds if b['start_ms']<=start<b['end_ms']),None)


def _count(items):return {'value':len(items),'numerator':None,'denominator':None,'unknown':0}


def _ratio(items,key='success'):
    known=[i for i in items if i.get(key) is not None];good=sum(1 for i in known if i[key])
    return {'value':round(100*good/len(known),1) if known else None,'numerator':good,'denominator':len(known),'unknown':len(items)-len(known)}


def _on_target(shot):return shot.get('on_target') is True or shot.get('outcome') in ('goal','saved')


def _values(records,blocked_ids):
    by_kind=lambda kind:[r for r in records if r['kind']==kind]
    shots=[r for r in records if r.get('counts_as_shot')]
    return {
        'shots_total':_count(shots),
        'shots_on_target':_count([s for s in shots if _on_target(s)]),
        'shots_off_target':_count([s for s in shots if s.get('outcome')=='off_target' or (s.get('on_target') is False and s['id'] not in blocked_ids)]),
        'shots_blocked':_count([s for s in shots if s['id'] in blocked_ids]),
        'passes_total':_count(by_kind('pass')),
        'passes_accurate':_ratio(by_kind('pass')),
        'carries_successful':_ratio(by_kind('carry')),
        'duels_won':_ratio(by_kind('duel')),
        'recoveries':_count(by_kind('recovery')),
        'shot_blocks':_count(by_kind('shot_block')),
        'turnovers':_count(by_kind('turnover')),
        'saves':_count(by_kind('save')),
        'distribution_accurate':_ratio(by_kind('distribution')),
        'errors':_count(by_kind('error')),
    }


def team_action_stats(version,*,published,period='all'):
    doc=version.document;records=version.canonical_actions or [];bounds=_periods(version)
    keys={'all',*(b['key'] for b in bounds)}
    if period not in keys:raise DomainError('validation','Такого периода нет в версии действий',status=422)
    blocked_ids={r.get('shot_id') for r in records if r['kind']=='shot_block' and r.get('shot_id')}
    untimed=0
    if period!='all':
        selected=[r for r in records if _period_of(r,bounds)==period]
        untimed=sum(1 for r in records if _period_of(r,bounds) is None)
    else:selected=records
    coverage={category:_coverage(doc,category) for category in {row[3] for row in ROWS}}
    values={side:_values([r for r in selected if r.get('side')==side],blocked_ids) for side in SIDES}
    rows=[]
    for key,label,group,category,unit in ROWS:
        present=any(values[s][key]['value'] or values[s][key]['unknown'] for s in SIDES)
        # Строка без записей и без объявленной полноты — это отсутствие источника, а не ноль.
        if not present and coverage[category]=='unknown':continue
        rows.append({'key':key,'label':label,'group':group,'category':category,'unit':unit,'coverage':coverage[category],
            'home':values['home'][key],'away':values['away'][key]})
    shots=[{'id':r['id'],'side':r.get('side'),'player_id':r.get('player_id'),'x':r['start_xy'][0],'y':r['start_xy'][1],
            'goal':bool(r.get('counts_as_player_goal')),'on_target':_on_target(r),'blocked':r['id'] in blocked_ids,
            'outcome':r.get('outcome') or 'unknown','period':_period_of(r,bounds),'start_ms':r.get('start_ms')}
        for r in selected if r.get('counts_as_shot') and r.get('start_xy') and r.get('side') in SIDES]
    pitch=(version.provenance or {}).get('pitch')
    return {'source':{'action_version_id':version.id,'revision':version.revision,'status':version.status,'published':published,
            'clock_basis':doc.get('clock_basis'),'analysis_scope':doc.get('analysis_scope','unknown')},
        'periods':[{'key':'all','label':'Весь матч'},*({'key':b['key'],'label':b['label']} for b in bounds)],
        'period':period,'untimed':untimed,'coverage':coverage,'rows':rows,'shots':shots,
        'pitch':{'length_m':pitch['length_m'],'width_m':pitch['width_m']} if pitch else None}


def public_action_stats(db,match_id,period='all'):
    pub=db.scalar(select(RatingMatchPublication).where(RatingMatchPublication.match_id==match_id))
    version=db.get(ActionVersion,pub.action_version_id) if pub and pub.action_version_id else None
    if version is None:raise DomainError('not_found','Действия матча не опубликованы',status=404)
    return team_action_stats(version,published=True,period=period)


def private_action_stats(db,match_id,period='all'):
    """Кабинет: последняя подтверждённая версия, иначе последняя на проверке."""
    versions=list(db.scalars(select(ActionVersion).where(ActionVersion.match_id==match_id).order_by(ActionVersion.revision.desc())))
    version=next((v for v in versions if v.status=='confirmed'),versions[0] if versions else None)
    if version is None:raise DomainError('not_found','Версий действий пока нет',status=404)
    pub=db.scalar(select(RatingMatchPublication).where(RatingMatchPublication.match_id==match_id))
    return team_action_stats(version,published=bool(pub and pub.action_version_id==version.id),period=period)
