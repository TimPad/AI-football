from copy import deepcopy
from collections import defaultdict
from aifootball.ratings.aggregate import tournament_rating
from aifootball.ratings.explanation import explain_rating
from sqlalchemy import select
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.tournaments.models import Tournament
from aifootball.service.catalog.models import Player
from aifootball.service.ratings.models import TournamentRatingSnapshot,PlayerRatingRow,RatingPolicyVersion,RatingReferenceVersion
from aifootball.service.ratings.calculation import rating_state,current_policy,snapshot_view,make_summaries,summary_facts
from aifootball.service.ratings.inputs import selected_inputs,digest


def overview(db,tid):
    get_entity(db,Tournament,tid);state=rating_state(db,tid)
    snapshots=list(db.scalars(select(TournamentRatingSnapshot).where(TournamentRatingSnapshot.tournament_id==tid).order_by(TournamentRatingSnapshot.created_at.desc())))
    selected,private_manifest=selected_inputs(db,tid,'private')
    _,public_manifest=selected_inputs(db,tid,'public')
    policies={p.id:p.content_hash for p in db.scalars(select(RatingPolicyVersion).where(RatingPolicyVersion.id.in_({s.policy_id for s in snapshots})))}
    def metadata(s):
        manifest=private_manifest if s.scope=='private' else public_manifest
        stale=digest({'sources':manifest,'policy':policies[s.policy_id],'settings':s.settings})!=s.source_fingerprint
        return {**snapshot_view(s,state),'stale':stale}
    return {'revision':state.revision if state else 0,'policy':current_policy(),
        'private_snapshot_id':state.private_snapshot_id if state else None,'public_snapshot_id':state.public_snapshot_id if state else None,
        'policy_approved':bool(state and state.public_policy_id),
        'snapshots':[metadata(s) for s in snapshots],
        'sources':[{'match_id':m.id,'protocol_id':p.id if p else None,'published_protocol_id':m.published_version_id,
            'participation_id':part.id if part else None,'action_id':action.id if action else None,
            'active_analysis_run_id':m.active_analysis_run_id,'published_analysis_run_id':m.published_analysis_run_id} for m,p,part,action,run,metrics in selected]}


def resolve_snapshot(db,tid,snapshot_id,scope):
    get_entity(db,Tournament,tid);state=rating_state(db,tid)
    if snapshot_id is None:snapshot_id=(state.public_snapshot_id if scope=='public' else state.private_snapshot_id) if state else None
    if snapshot_id is None:return None
    snapshot=get_entity(db,TournamentRatingSnapshot,snapshot_id)
    if snapshot.tournament_id!=tid or scope=='public' and (snapshot.scope!='public' or snapshot.published_at is None):
        raise DomainError('not_found','Опубликованный срез не найден',status=404)
    return snapshot


def _rows(db,snapshot):
    return [deepcopy(r.payload) for r in db.scalars(select(PlayerRatingRow).where(PlayerRatingRow.snapshot_id==snapshot.id,PlayerRatingRow.match_id.is_not(None)).order_by(PlayerRatingRow.match_id,PlayerRatingRow.player_id,PlayerRatingRow.role))]


def get_rankings(db,tid,snapshot_id=None,filters=None,pagination=None,*,scope='private'):
    filters=filters or {};pagination=pagination or {};limit=pagination.get('limit',50);offset=pagination.get('offset',0)
    snapshot=resolve_snapshot(db,tid,snapshot_id,scope)
    empty={'snapshot_id':None,'scope':scope,'items':[],'total':0,'limit':limit,'offset':offset,'reason':'not_calculated','filters':filters}
    if snapshot is None:return empty
    policy=get_entity(db,RatingPolicyVersion,snapshot.policy_id).document
    rows=_rows(db,snapshot)
    if filters.get('team_id'):rows=[r for r in rows if r['team_id']==str(filters['team_id'])]
    if filters.get('stage_label'):rows=[r for r in rows if r['stage_label']==filters['stage_label']]
    role=filters.get('position')
    if role is not None and role not in policy['roles']:raise DomainError('position','Выберите известную позицию')
    values=make_summaries(rows,policy,role)
    if filters.get('qualification'):values=[v for v in values if v['qualification']==filters['qualification']]
    reference=get_entity(db,RatingReferenceVersion,snapshot.reference_id)
    return {'snapshot_id':snapshot.id,'calculated_at':snapshot.created_at,'published_at':snapshot.published_at,'scope':snapshot.scope,
        'edition':{'model_version':policy['model_version'],'reference_version':reference.content_hash,
            'profile_id':snapshot.settings['profile_id'],'time_basis':snapshot.settings['time_basis']},
        'items':values[offset:offset+limit],'total':len(values),'limit':limit,'offset':offset,'filters':filters,'label':policy['label']}


def player_history(db,pid,tid,snapshot_id=None,*,scope='private'):
    get_entity(db,Player,pid);snapshot=resolve_snapshot(db,tid,snapshot_id,scope)
    if snapshot is None:return {'snapshot_id':None,'summary':[],'matches':[]}
    values=[r for r in _rows(db,snapshot) if r['player_id']==str(pid)]
    policy=get_entity(db,RatingPolicyVersion,snapshot.policy_id).document
    return {'snapshot_id':snapshot.id,'summary':make_summaries(values,policy),'matches':sorted(values,key=lambda r:(r['scheduled_at'],r['match_id'],r['role']))}


def match_ratings(db,mid,snapshot_id=None,*,scope='private'):
    from aifootball.service.matches.models import Match
    match=get_entity(db,Match,mid);snapshot=resolve_snapshot(db,match.tournament_id,snapshot_id,scope)
    if snapshot is None:return {'snapshot_id':None,'items':[]}
    rows=[v for v in _rows(db,snapshot) if v['match_id']==str(mid)]
    policy=get_entity(db,RatingPolicyVersion,snapshot.policy_id).document
    groups=defaultdict(list)
    for row in rows:groups[row['player_id']].append(row)
    overall=[]
    for pid,segments in groups.items():
        combined=tournament_rating(segments,match_min_minutes=policy['match_min_minutes'],coverage_min=policy['coverage_min'])
        match_value=combined['matches'][0] if combined['matches'] else {'score':None,'coverage':None}
        value=deepcopy(segments[0]);value.update(role='overall',score=match_value['score'],
            display_rating=None if match_value['score'] is None else round(1+9*match_value['score']/100,1),
            coverage=match_value['coverage'],eligible_play_minutes=None if any(v['eligible_play_minutes'] is None for v in segments) else sum(v['eligible_play_minutes'] for v in segments),
            played_minutes=combined['played_minutes'],facts=summary_facts(segments),moments=[])
        value['reasons']=sorted({reason for r in segments for reason in r['reasons']})
        if value['score'] is None and not value['reasons']:value['reasons']=['short_appearance_or_insufficient_coverage']
        if len(segments)>1:value['components']={};value['contributions']={};value['feature_scores']={}
        value['explanation']=explain_rating({**value,'scope':scope},value['facts'],[])
        overall.append(value)
    return {'snapshot_id':snapshot.id,'items':rows,'overall':overall}
