from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from uuid import UUID
import json
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from aifootball.ratings.reference import build_reference
from aifootball.ratings.scoring import score_match,policy_hash
from aifootball.ratings.aggregate import rank_players
from aifootball.ratings.features import combine_rate
from aifootball.ratings.schema import MetricFact
from aifootball.service.common import get_entity
from aifootball.service.db import utcnow
from aifootball.service.errors import DomainError
from aifootball.service.tournaments.models import Tournament
from aifootball.service.matches.models import Match
from aifootball.service.ratings.models import RatingPolicyVersion,RatingReferenceVersion,TournamentRatingSnapshot,PlayerRatingRow,TournamentRatingState,RatingMatchPublication,RatingCommand,ParticipationVersion,ActionVersion
from aifootball.service.ratings.inputs import selected_inputs,performances,digest


def current_policy():return json.loads((Path(__file__).resolve().parents[4]/'configs/ratings/role-profile-v1.json').read_text())


def rating_state(db,tid,*,create=False):
    value=db.scalar(select(TournamentRatingState).where(TournamentRatingState.tournament_id==tid))
    if value is None and create:value=TournamentRatingState(tournament_id=tid,revision=0);db.add(value);db.flush()
    return value


def _policy_version(db):
    doc=current_policy();hashed=policy_hash(doc)
    value=db.scalar(select(RatingPolicyVersion).where(RatingPolicyVersion.content_hash==hashed))
    if value is None:value=RatingPolicyVersion(content_hash=hashed,document=doc);db.add(value);db.flush()
    return value


def _command(db,tid,actor_id,request_id,kind,payload):
    get_entity(db,Tournament,tid,lock=True)
    hashed=digest({'actor_id':str(actor_id),'kind':kind,'payload':payload})
    old=db.scalar(select(RatingCommand).where(RatingCommand.tournament_id==tid,RatingCommand.request_id==request_id))
    if old and (old.request_hash!=hashed or old.actor_id!=actor_id):raise DomainError('idempotency_conflict','Ключ уже использован для другой команды',status=409)
    return old,hashed


def _remember(db,tid,actor,request_id,hashed,response):
    response=jsonable_encoder(response)
    db.add(RatingCommand(tournament_id=tid,actor_id=actor,request_id=request_id,request_hash=hashed,response=response));db.flush();return response


def _expected(state,revision):
    if state.revision!=revision:raise DomainError('revision_conflict','Аналитика изменена. Обновите страницу.',status=409,current_revision=state.revision)


def snapshot_view(snapshot,state):
    return {'snapshot_id':snapshot.id,'revision':state.revision,'scope':snapshot.scope,'calculated_at':snapshot.created_at,
        'published_at':snapshot.published_at,'source_fingerprint':snapshot.source_fingerprint,'summary':snapshot.summary,
        'settings':snapshot.settings}


def summary_facts(rows):
    result={};keys=set().union(*(r.get('facts',{}) for r in rows)) if rows else set()
    for key in keys:
        values=[r.get('facts',{}).get(key) for r in rows];known=[MetricFact(**v) for v in values if v is not None]
        unit=known[0].unit
        if len(known)!=len(values):fact=MetricFact(None,None,None,unit,'unknown','missing_category')
        elif unit in ('count/10min','percent'):fact=combine_rate(known)
        elif all(v.value is not None and v.completeness=='complete' for v in known):
            value=max(v.value for v in known) if key in ('vmax_ms','sustained_vmax_ms') else sum(v.value for v in known)
            fact=MetricFact(value,value,None,unit,'complete',None)
        else:fact=MetricFact(None,sum(v.numerator or 0 for v in known),None,unit,'partial','incomplete_aggregate')
        result[key]=asdict(fact)
    return result


def make_summaries(rows,policy,role=None):
    summaries=rank_players(rows,role=role,policy=policy)
    for item in summaries:
        selected=[r for r in rows if r['player_id']==item['player_id'] and (role is None or r['role']==role)]
        item['display_name']=selected[-1]['display_name'];item['facts']=summary_facts(selected)
        teams={(r['team_id'],r['team_name']) for r in selected};item['teams']=[{'id':tid,'name':name} for tid,name in sorted(teams)]
        item['reasons']=sorted({reason for r in selected for reason in r['reasons']}) if item['score'] is None else []
        item.pop('matches',None)
    return summaries


def calculate_snapshot(db,tid,actor_id,request_id,*,scope='private',expected_revision=0,profile_id='per10',time_basis='reviewed_effective',level='amateur',cutoff=None):
    payload={'scope':scope,'expected_revision':expected_revision,'profile_id':profile_id,'time_basis':time_basis,'level':level,'cutoff':cutoff}
    old,hashed=_command(db,tid,actor_id,request_id,'calculate',payload)
    if old:return old.response
    state=rating_state(db,tid,create=True);_expected(state,expected_revision);policy=_policy_version(db)
    if scope=='public' and state.public_policy_id!=policy.id:raise DomainError('unpublished_policy','Сначала разрешите публикацию текущей методики вместе с источниками')
    settings={'scope':scope,'profile_id':profile_id,'time_basis':time_basis,'level':level,'cutoff':cutoff or utcnow().isoformat()}
    selected,manifest=selected_inputs(db,tid,scope,lock=True)
    rows,details=performances(db,tid,selected,settings,scope)
    if rows:reference=build_reference(rows,policy=policy.document,cutoff=settings['cutoff'])
    else:
        reference={'model_version':policy.document['model_version'],'policy_hash':policy.content_hash,'profile_id':profile_id,
            'time_basis':time_basis,'tournament_id':str(tid),'level':level,'cutoff':settings['cutoff'],'cohorts':{}}
        reference['reference_version']=digest(reference)
    ref=db.scalar(select(RatingReferenceVersion).where(RatingReferenceVersion.tournament_id==tid,RatingReferenceVersion.scope==scope,RatingReferenceVersion.content_hash==reference['reference_version']))
    if ref is None:
        ref=RatingReferenceVersion(tournament_id=tid,policy_id=policy.id,scope=scope,content_hash=reference['reference_version'],document=reference);db.add(ref);db.flush()
    fingerprint=digest({'sources':manifest,'policy':policy.content_hash,'settings':settings})
    # Persist match/role payloads once, with frozen names/teams and source links.
    values=[]
    for row in rows:
        detail=details[(row.match_id,row.player_id,row.role)];score=score_match(row.facts,role=row.role,policy=policy.document,reference=reference)
        reasons=detail['reasons']+score['reasons']
        if row.eligible_play_s is None or row.coverage is None or row.coverage<policy.document['coverage_min']:
            score['score']=None;score['display_rating']=None;reasons.append('unknown_or_insufficient_role_coverage')
        values.append({**detail,'match_id':row.match_id,'player_id':row.player_id,'role':row.role,
            'eligible_play_minutes':None if row.eligible_play_s is None else row.eligible_play_s/60,
            'played_minutes':None if row.eligible_play_s is None else row.eligible_play_s/60,
            'coverage':row.coverage,'score':score['score'],'display_rating':score['display_rating'],
            'components':score['components'],'contributions':score['contributions'],'feature_scores':score['feature_scores'],
            'facts':{k:asdict(v) for k,v in row.facts.items()},'reasons':sorted(set(reasons)),
            'model_version':policy.document['model_version'],'reference_version':reference['reference_version'],'profile_id':profile_id,'time_basis':time_basis})
    summary={'match_count':len({r.match_id for r in rows}),'player_count':len({r.player_id for r in rows}),
        'rated_player_matches':len({(r['player_id'],r['match_id']) for r in values if r['score'] is not None}),
        'selected_match_count':len(manifest),'reference':{role:{key:c[key] for key in ('available','eligible_player_matches')} for role,c in reference['cohorts'].items()}}
    snapshot=TournamentRatingSnapshot(tournament_id=tid,policy_id=policy.id,reference_id=ref.id,created_by=actor_id,
        scope=scope,source_fingerprint=fingerprint,inputs=manifest,settings=settings,summary=summary)
    db.add(snapshot);db.flush()
    for value in values:db.add(PlayerRatingRow(snapshot_id=snapshot.id,player_id=UUID(value['player_id']),match_id=UUID(value['match_id']),role=value['role'],payload=value))
    for role in (None,*policy.document['roles']):
        for value in make_summaries(values,policy.document,role):db.add(PlayerRatingRow(snapshot_id=snapshot.id,player_id=UUID(value['player_id']),match_id=None,role=role or 'overall',payload=value))
    if scope=='private':state.private_snapshot_id=snapshot.id
    state.revision+=1;db.flush()
    return _remember(db,tid,actor_id,request_id,hashed,snapshot_view(snapshot,state))


def publish_sources(db,mid,actor,data):
    # Read immutable tournament membership before locking in the same order as calc.
    tid=db.scalar(select(Match.tournament_id).where(Match.id==mid))
    if tid is None:raise DomainError('not_found','Матч не найден',status=404)
    old,hashed=_command(db,tid,actor,data.request_id,'publish-sources',{'match_id':str(mid),**data.model_dump(mode='json',exclude={'request_id'})})
    if old:return old.response
    state=rating_state(db,tid,create=True);_expected(state,data.expected_revision)
    match=get_entity(db,Match,mid,lock=True)
    if match.revision!=data.expected_match_revision:raise DomainError('revision_conflict','Матч изменён',status=409,current_revision=match.revision)
    part=get_entity(db,ParticipationVersion,data.participation_version_id) if data.participation_version_id else None
    action=get_entity(db,ActionVersion,data.action_version_id) if data.action_version_id else None
    for value in (part,action):
        if value and (value.match_id!=mid or value.status!='confirmed'):raise DomainError('publication_source','Выберите подтверждённую версию этого матча')
        if value and value.source_protocol_version_id!=match.published_version_id:raise DomainError('publication_source','Сначала опубликуйте соответствующую версию протокола')
        if value and value.source_analysis_run_id and value.source_analysis_run_id!=match.published_analysis_run_id:raise DomainError('publication_source','Сначала опубликуйте соответствующую версию видеоанализа')
    if action and (part is None or action.source_participation_version_id!=part.id):raise DomainError('publication_source','Действия должны ссылаться на выбранное участие')
    pub=db.scalar(select(RatingMatchPublication).where(RatingMatchPublication.match_id==mid))
    if pub is None:pub=RatingMatchPublication(match_id=mid,created_by=actor,revision=0);db.add(pub)
    pub.participation_version_id=part.id if part else None;pub.action_version_id=action.id if action else None;pub.revision+=1
    if data.approve_policy:state.public_policy_id=_policy_version(db).id
    state.revision+=1;db.flush()
    return _remember(db,tid,actor,data.request_id,hashed,{'revision':state.revision,'match_id':mid,
        'participation_version_id':pub.participation_version_id,'action_version_id':pub.action_version_id,'policy_approved':state.public_policy_id is not None})


def publish_snapshot(db,tid,actor,data):
    old,hashed=_command(db,tid,actor,data.request_id,'publish',data.model_dump(mode='json',exclude={'request_id'}))
    if old:return old.response
    state=rating_state(db,tid,create=True);_expected(state,data.expected_revision)
    snapshot=get_entity(db,TournamentRatingSnapshot,data.snapshot_id)
    if snapshot.tournament_id!=tid or snapshot.scope!='public':raise DomainError('publication_snapshot','Публикуется отдельный срез из публичных источников этого турнира')
    if snapshot.policy_id!=state.public_policy_id:raise DomainError('unpublished_policy','Методика не разрешена к публикации')
    _,manifest=selected_inputs(db,tid,'public',lock=True)
    policy=get_entity(db,RatingPolicyVersion,snapshot.policy_id)
    current=digest({'sources':manifest,'policy':policy.content_hash,'settings':snapshot.settings})
    if current!=snapshot.source_fingerprint:raise DomainError('stale_snapshot','Источники изменились; пересчитайте публичный срез',status=409)
    snapshot.published_at=snapshot.published_at or utcnow();state.public_snapshot_id=snapshot.id;state.revision+=1;db.flush()
    return _remember(db,tid,actor,data.request_id,hashed,snapshot_view(snapshot,state))
