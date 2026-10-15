from copy import deepcopy
from hashlib import sha256
from uuid import UUID,uuid4
from sqlalchemy import select,func
from aifootball.analytics.exchange import canonical
from aifootball.ratings.actions import canonical_actions
from aifootball.ratings.validate import intervals,intersection
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.matches.models import Match
from aifootball.service.matches.operations import get_match_view
from aifootball.service.protocol.models import ProtocolVersion
from aifootball.service.analysis.models import AnalysisRun,AnalysisAssignment,AnalysisJob
from aifootball.service.analysis.understanding import _effective
from aifootball.service.analysis.jobs import prior_command,remember
from aifootball.service.ratings.models import ActionVersion,ParticipationVersion
from aifootball.service.ratings.operations import participation_overview


def action_view(value):
    return {key:getattr(value,key) for key in ('id','match_id','revision','status','created_at','created_by',
        'context_hash','document','provenance','lineup','canonical_actions')}


def action_overview(db,match_id):
    context=participation_overview(db,match_id);match=get_entity(db,Match,match_id)
    versions=list(db.scalars(select(ActionVersion).where(ActionVersion.match_id==match_id).order_by(ActionVersion.revision.desc())))
    hall=match.hall_snapshot
    return {key:context[key] for key in ('match_id','match_revision','lineup','rules','protocol_versions','analysis_runs')}|{
        'revision':versions[0].revision if versions else 0,'current':action_view(versions[0]) if versions else None,
        'versions':[{'id':v.id,'revision':v.revision,'status':v.status,'created_at':v.created_at} for v in versions],
        'participation_versions':context['versions'],
        'pitch':{'length_m':hall['pitch_length_m'],'width_m':hall['pitch_width_m']} if hall else None}


def _validate_coverage(doc,lineup):
    known={p['player_id'] for p in lineup}
    for category,declarations in doc['completeness'].items():
        by_player={}
        if len(declarations)>2000:raise ValueError('Too many category declarations')
        for item in declarations:
            people=item['player_ids'] if item['player_ids'] is not None else sorted(known)
            if len(people)!=len(set(people)) or not set(people)<=known:raise ValueError('Unknown/duplicate category player')
            spans=intervals(item['intervals'] if item['intervals'] is not None else [[0,doc['duration_ms']]],doc['duration_ms'])
            item['intervals']=spans
            for pid in people:by_player.setdefault(pid,[]).extend(spans)
        for spans in by_player.values():intervals(spans,doc['duration_ms'])


def save_actions(db,match_id,actor_id,data):
    old,hashed=prior_command(db,match_id,actor_id,data.request_id,'performance-actions',data.model_dump(mode='json',exclude={'request_id'}))
    if old:return old.response
    match=get_entity(db,Match,match_id,lock=True)
    latest=db.scalar(select(func.max(ActionVersion.revision)).where(ActionVersion.match_id==match_id)) or 0
    if data.expected_revision!=latest or data.expected_match_revision!=match.revision:
        raise DomainError('revision_conflict','Действия или протокол изменены; обновите данные',status=409,current_revision=latest)
    doc=data.document.model_dump(mode='json');view=get_match_view(db,match_id)
    rules=view['regulation']['rules'];lineup=view['lineup'];participation=None;protocol=None;source=None
    if doc['source_participation_version_id']:
        participation=get_entity(db,ParticipationVersion,UUID(doc['source_participation_version_id']))
        if participation.match_id!=match_id or participation.status!='confirmed':raise DomainError('action_source','Выберите подтверждённое участие этого матча')
        if doc['clock_basis']!=participation.document['clock_basis'] or doc['duration_ms']!=participation.document['duration_ms']:
            raise DomainError('action_clock','Разметка и участие должны использовать одну шкалу и длительность')
        lineup=participation.lineup;rules=participation.provenance['regulation']
        for field in ('source_protocol_version_id','source_analysis_run_id'):
            parent=getattr(participation,field)
            if doc[field] is None and parent is not None:doc[field]=str(parent)
    if doc['source_protocol_version_id']:
        protocol=get_entity(db,ProtocolVersion,UUID(doc['source_protocol_version_id']))
        if protocol.match_id!=match_id:raise DomainError('action_source','Протокол другого матча')
        if participation and participation.source_protocol_version_id and protocol.id!=participation.source_protocol_version_id:
            raise DomainError('action_source','Версия протокола не совпадает со снимком участия')
        rules=protocol.snapshot['regulation']['rules'];lineup=protocol.snapshot['lineup']
    if doc['source_analysis_run_id']:
        source=get_entity(db,AnalysisRun,UUID(doc['source_analysis_run_id']))
        if source.match_id!=match_id or source.status!='confirmed':raise DomainError('action_source','Выберите подтверждённый отчёт этого матча')
    if doc['clock_basis']=='video':
        if source is None or doc['duration_ms']!=round(source.manifest['source_video']['duration_s']*1000):raise DomainError('action_clock','Укажите запись и её точную длительность')
        scope=(source.understanding or {}).get('source',{}).get('analysis_scope','unknown')
        if doc['analysis_scope']=='full_match' and scope in ('highlights','continuous_excerpt'):raise DomainError('action_scope','Фрагмент видеозаписи не является полным матчем')
    else:
        minimum=sum(rules['periods_s'])*1000
        maximum=minimum+(sum(rules['extra']['periods_s'])*1000 if rules['extra']['enabled'] else 0)
        if doc['duration_ms']>maximum or (doc['analysis_scope']=='full_match' and doc['duration_ms']<minimum):raise DomainError('action_clock','Длительность не соответствует регламенту и полноте')
    lineup=[{key:p[key] for key in ('player_id','side','shirt_number','display_name')} for p in lineup]
    roster={p['player_id']:p['side'] for p in lineup};hall=match.hall_snapshot
    pitch={'length_m':hall['pitch_length_m'],'width_m':hall['pitch_width_m']} if hall else None
    if source:pitch=get_entity(db,AnalysisJob,source.job_id).context['pitch']
    reviewed={e['id']:e for e in _effective(source) if e['review_status'] in ('accepted','corrected')} if source else {}
    assigned={a.track_id:str(a.player_id) for a in db.scalars(select(AnalysisAssignment).where(AnalysisAssignment.run_id==source.id,AnalysisAssignment.player_id.is_not(None)))} if source else {}
    version_id=uuid4();prepared=[]
    try:
        _validate_coverage(doc,lineup)
        for action in doc['actions']:
            if (action['success'] is True and action['outcome']=='failure') or (action['success'] is False and action['outcome']=='success'):
                raise ValueError('Action success conflicts with outcome')
            if (action['on_target'] is False and action['outcome'] in ('goal','saved')) or (action['on_target'] is True and action['outcome']=='off_target'):
                raise ValueError('Shot target conflicts with outcome')
            for field in ('player_id','recipient_id','opponent_id'):
                if action[field] is not None and action[field] not in roster:raise ValueError('Player is outside selected roster')
            side=roster.get(action['player_id'])
            if action['side'] is not None and side is not None and action['side']!=side:raise ValueError('Action side conflicts with player')
            action['side']=action['side'] or side
            for field in ('recipient_id','opponent_id'):
                if action[field] is not None and action['side'] is not None:
                    same=roster[action[field]]==action['side']
                    if same!=(field=='recipient_id'):raise ValueError('Action recipient/opponent has wrong side')
            if action['start_ms'] is None and action['end_ms'] is not None:raise ValueError('End without start')
            if action['start_ms'] is not None:
                if action['end_ms'] is None:action['end_ms']=action['start_ms']
                if not 0<=action['start_ms']<=action['end_ms']<doc['duration_ms']:raise ValueError('Action outside timeline')
            for point in (action['start_xy'],action['end_xy']):
                if point is not None and (pitch is None or point[0]>pitch['length_m'] or point[1]>pitch['width_m']):raise ValueError('Coordinates require actual hall geometry')
            if action['penalty_conceded'] and action['kind']!='error':raise ValueError('Penalty-conceded attribution requires an error fact')
            if participation and action['player_id'] and action['start_ms'] is not None:
                person=next((p for p in participation.document['players'] if p['player_id']==action['player_id']),None)
                if person and person['presence'] is not None and person['completeness']=='complete' and not any(a<=action['start_ms']<b for a,b in person['presence']):
                    raise ValueError('Player was not on pitch at the action time')
            refs=[{'kind':'manual','id':action['id'],'version_id':str(version_id)}]
            if action['source_episode_id'] is not None:
                event=reviewed.get(action['source_episode_id'])
                if event is None:raise ValueError('Episode is not accepted in the selected confirmed version')
                video_ms=action['start_ms'] if doc['clock_basis']=='video' else action['source_video_ms']
                if video_ms is None or not max(0,event['start_ms']-2000)<=video_ms<=event['end_ms']+2000:raise ValueError('Explicit source-video anchor required for episode')
                actors={assigned[tid] for tid in event['track_ids'] if tid in assigned}
                if action['player_id'] and event['track_ids'] and action['player_id'] not in actors:raise ValueError('Episode actor must match saved player assignment')
                if action['kind']=='goal_candidate' and event['kind']!='goal_candidate':raise ValueError('Episode was not reviewed as a goal candidate')
                refs.append({'kind':'understanding','id':event['id'],'run_id':str(source.id),'video_ms':video_ms,'evidence_ids':event['evidence_ids']})
            prepared.append({**action,'clock_basis':doc['clock_basis'],'source_refs':refs})
        protocol_doc=deepcopy(protocol.snapshot['protocol'] if protocol else match.protocol)
        offsets={};cursor=0
        for index,seconds in enumerate(rules['periods_s']+(rules['extra']['periods_s'] if rules['extra']['enabled'] else []),1):
            offsets[str(index)]=cursor;cursor+=seconds*1000
        records=canonical_actions({**protocol_doc,'clock_basis':doc['clock_basis'],'period_offsets_ms':offsets},prepared,doc['links'])
    except ValueError as exc:raise DomainError('action_facts',str(exc)) from exc
    provenance={'match_revision':match.revision,'protocol_version_id':str(protocol.id) if protocol else None,
        'protocol':protocol_doc,'protocol_sha256':sha256(canonical(protocol_doc)).hexdigest(),
        'regulation':rules,'pitch':pitch,'participation_version_id':str(participation.id) if participation else None,
        'analysis_run_id':str(source.id) if source else None,'source_kind':'manual_verified' if data.status=='confirmed' else 'manual_draft'}
    version=ActionVersion(id=version_id,match_id=match_id,revision=latest+1,status=data.status,created_by=actor_id,
        source_participation_version_id=participation.id if participation else None,source_analysis_run_id=source.id if source else None,
        source_protocol_version_id=protocol.id if protocol else None,context_hash=sha256(canonical({'lineup':lineup,'provenance':provenance})).hexdigest(),
        document=doc,lineup=lineup,provenance=provenance,canonical_actions=records)
    db.add(version);db.flush()
    return remember(db,match_id,actor_id,data.request_id,hashed,action_view(version))
