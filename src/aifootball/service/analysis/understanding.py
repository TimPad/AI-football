"""Private projections/review commands. Never mutates the official protocol."""
from copy import deepcopy
from sqlalchemy import select
from aifootball.service.common import get_entity
from aifootball.service.matches.models import Match
from aifootball.service.analysis.models import AnalysisRun,AnalysisJob,AnalysisAssignment,AnalysisUnderstandingDecision
from aifootball.service.analysis.jobs import prior_command,remember
from aifootball.service.errors import DomainError
from aifootball.understanding.identity import resolve_identity
from aifootball.understanding.schema import validate_understanding

LABELS={'goal_candidate':'Возможный гол','shot_candidate':'Возможный удар','save_candidate':'Возможное отражение удара',
        'kickoff':'Начальный удар','kick_in':'Ввод из-за боковой','corner':'Угловой','timeout':'Тайм-аут',
        'substitution_candidate':'Возможная замена','keeper_out_candidate':'Выход вратаря',
        'free_kick_candidate':'Возможный штрафной','penalty_candidate':'Возможный пенальти',
        'pressing_candidate':'Признаки прессинга','compact_block_candidate':'Компактный блок','unknown':'Эпизод'}


def _effective(run):
    result=[]
    for event in (run.understanding or {}).get('events',[]):
        decision=run.understanding_reviews.get(event['id'])
        if decision and decision['decision']=='rejected':continue
        value={**event,**((decision or {}).get('correction') or {}),'review_status':decision['decision'] if decision else None}
        result.append(value)
    return result


def get_understanding(db,run):
    job=get_entity(db,AnalysisJob,run.job_id)
    suggestions=resolve_identity((run.understanding or {}).get('observations',[]),job.context['rosters'],
        side_map=run.side_map if run.side_map_verified else None,
        track_intervals={track['track_id']:track['intervals'] for track in run.tracks['tracks']},
        track_teams={track['track_id']:track['team'] for track in run.tracks['tracks']})
    assignments={row.track_id:str(row.player_id) for row in db.scalars(select(AnalysisAssignment).where(
        AnalysisAssignment.run_id==run.id,AnalysisAssignment.player_id.is_not(None)))}
    events=_effective(run);summary=[]
    for event in events:
        if event['review_status'] not in ('accepted','corrected'):continue
        seconds=event['start_ms']//1000
        summary.append({'text':f"{LABELS[event['kind']]} · {seconds//60:02}:{seconds%60:02} исходника",
            'event_ids':[event['id']],'metric_refs':[],
            'player_ids':sorted({assignments[tid] for tid in event['track_ids'] if tid in assignments})})
    history=[{'id':str(row.id),'event_id':row.event_id,'actor_id':str(row.actor_id),
              'revision':row.revision,'before':row.before,'after':row.after,'created_at':row.created_at}
             for row in db.scalars(select(AnalysisUnderstandingDecision).where(AnalysisUnderstandingDecision.run_id==run.id)
                .order_by(AnalysisUnderstandingDecision.revision))]
    return {'run_id':str(run.id),'match_id':str(run.match_id),'source_run_id':str(run.source_run_id) if run.source_run_id else None,
            'status':run.status,'revision':run.revision,'understanding':run.understanding,
            'reviews':run.understanding_reviews,'side_map_verified':run.side_map_verified,
            'identity_suggestions':suggestions,'effective_events':events,'verified_summary':summary,'history':history}


def review_understanding(db,match_id,run_id,actor_id,data):
    payload={'run_id':str(run_id),**data.model_dump(mode='json',exclude={'request_id'})}
    prior,hashed=prior_command(db,match_id,actor_id,data.request_id,'understanding-review',payload)
    if prior:return prior.response
    get_entity(db,Match,match_id,lock=True)
    run=get_entity(db,AnalysisRun,run_id,lock=True)
    if run.match_id!=match_id:raise DomainError('not_found','Отчёт не найден',status=404)
    if run.revision!=data.expected_revision:raise DomainError('revision_conflict','Проверка эпизодов изменена',status=409,current_revision=run.revision)
    if run.status!='review':raise DomainError('immutable_analysis','Создайте новую версию проверки',status=409)
    if run.understanding is None:raise DomainError('understanding_missing','В этой версии нет анализа эпизодов')
    original=next((item for item in run.understanding['events'] if item['id']==data.event_id),None)
    if original is None:raise DomainError('not_found','Эпизод не найден',status=404)
    if (data.decision=='corrected')!=(data.correction is not None):raise DomainError('understanding_correction','Исправлению нужны изменённые поля; другим решениям они не нужны')
    before=deepcopy(run.understanding_reviews.get(data.event_id))
    current_correction=(before or {}).get('correction') or {}
    correction=({**current_correction,**data.correction} if data.decision=='corrected' else
                deepcopy(current_correction) if data.decision=='accepted' and current_correction else None)
    if data.correction is not None:
        if not data.correction or not set(data.correction)<=set(original)-{'id'}:
            raise DomainError('understanding_correction','Недопустимые поля исправления')
    if correction is not None:
        candidate=deepcopy(run.understanding)
        corrected={**original,**correction}
        candidate['events']=[corrected if item['id']==data.event_id else item for item in candidate['events']]
        try:
            job=get_entity(db,AnalysisJob,run.job_id)
            validate_understanding(candidate,manifest=run.manifest,tracks=run.tracks,rosters=job.context['rosters'])
        except ValueError as exc:raise DomainError('understanding_correction','Исправление нарушает границы, типы или ссылки эпизода') from exc
    if data.decision in ('accepted','corrected'):
        effective={**original,**(correction or {})}
        tracks={item['track_id']:item for item in run.tracks['tracks']}
        for tid in effective['track_ids']:
            # Candidate boundaries are uncertain, but another minute is not the same episode.
            if not any(max(a,effective['start_ms']/1000-2)<min(b,effective['end_ms']/1000+2) for a,b in tracks[tid]['intervals']):
                raise DomainError('understanding_time','Фрагмент игрока не наблюдался рядом с эпизодом')
    run.revision+=1
    after={'decision':data.decision,'correction':deepcopy(correction),'reason':data.reason.strip(),
           'actor_id':str(actor_id),'revision':run.revision}
    run.understanding_reviews={**run.understanding_reviews,data.event_id:after}
    db.add(AnalysisUnderstandingDecision(run_id=run.id,event_id=data.event_id,actor_id=actor_id,
                                       revision=run.revision,before=before,after=deepcopy(after)))
    db.flush()
    return remember(db,match_id,actor_id,data.request_id,hashed,get_understanding(db,run))
