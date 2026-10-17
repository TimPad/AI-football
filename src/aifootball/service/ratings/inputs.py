"""Batch source selection and per-role adapters. No inference of attendance from CV."""
from copy import deepcopy
from dataclasses import asdict,replace
from hashlib import sha256
from uuid import UUID
from sqlalchemy import select
from aifootball.analytics.exchange import canonical
from aifootball.ratings.actions import canonical_actions
from aifootball.ratings.features import build_features
from aifootball.ratings.schema import MatchPerformance,MetricFact
from aifootball.ratings.validate import intervals,intersection,duration_s,_remaining
from aifootball.service.matches.models import Match
from aifootball.service.matches.operations import get_match_view
from aifootball.service.protocol.models import ProtocolVersion
from aifootball.service.analysis.models import AnalysisRun,PlayerMatchMetric
from aifootball.service.ratings.models import ParticipationVersion,ActionVersion,RatingMatchPublication,is_auto
from aifootball.service.ratings.operations import participation_view


def digest(value):return sha256(canonical(value)).hexdigest()


def _prefer_manual(versions,belongs):
    """Последняя ручная версия матча главнее автоматической; из автоматических — та, что относится
    к выбранному прогону видеоанализа (belongs), иначе последняя."""
    manual,auto={},{}
    for v in versions:
        if not is_auto(v):manual[v.match_id]=v
        elif belongs(v) or not (v.match_id in auto and belongs(auto[v.match_id])):auto[v.match_id]=v
    return {**auto,**manual}


def selected_inputs(db,tid,scope,*,lock=False):
    query=select(Match).where(Match.tournament_id==tid).order_by(Match.id)
    if lock:query=query.with_for_update()
    matches=list(db.scalars(query));ids=[m.id for m in matches]
    protocols=list(db.scalars(select(ProtocolVersion).where(ProtocolVersion.match_id.in_(ids)).order_by(ProtocolVersion.number)))
    parts=list(db.scalars(select(ParticipationVersion).where(ParticipationVersion.match_id.in_(ids),ParticipationVersion.status=='confirmed').order_by(ParticipationVersion.revision)))
    actions=list(db.scalars(select(ActionVersion).where(ActionVersion.match_id.in_(ids),ActionVersion.status=='confirmed').order_by(ActionVersion.revision)))
    publications={v.match_id:v for v in db.scalars(select(RatingMatchPublication).where(RatingMatchPublication.match_id.in_(ids)))}
    run_of={m.id:m.active_analysis_run_id if scope=='private' else m.published_analysis_run_id for m in matches}
    latest_protocol={v.match_id:v for v in protocols};latest_part=_prefer_manual(parts,lambda v:v.source_analysis_run_id==run_of[v.match_id])
    latest_action=_prefer_manual(actions,lambda v:latest_part.get(v.match_id) is not None and v.source_participation_version_id==latest_part[v.match_id].id)
    pbyid={v.id:v for v in protocols};partbyid={v.id:v for v in parts};actionbyid={v.id:v for v in actions}
    run_ids={m.active_analysis_run_id if scope=='private' else m.published_analysis_run_id for m in matches}-{None}
    runs={v.id:v for v in db.scalars(select(AnalysisRun).where(AnalysisRun.id.in_(run_ids),AnalysisRun.status=='confirmed'))}
    metrics={}
    for value in db.scalars(select(PlayerMatchMetric).where(PlayerMatchMetric.run_id.in_(run_ids))):metrics[(value.run_id,str(value.player_id))]=value.metrics
    selected=[];manifest=[]
    for match in matches:
        pub=publications.get(match.id)
        protocol=latest_protocol.get(match.id) if scope=='private' else pbyid.get(match.published_version_id)
        part=latest_part.get(match.id) if scope=='private' else partbyid.get(pub.participation_version_id) if pub else None
        action=latest_action.get(match.id) if scope=='private' else actionbyid.get(pub.action_version_id) if pub else None
        run_id=match.active_analysis_run_id if scope=='private' else match.published_analysis_run_id;run=runs.get(run_id)
        # An unpublished match contributes no private data to a public cohort.
        if scope=='public' and protocol is None:continue
        item={'match_id':str(match.id),'status':match.status,'protocol_id':str(protocol.id) if protocol else None,
            'protocol_hash':digest(protocol.snapshot) if protocol else digest(match.protocol),
            'participation_id':str(part.id) if part else None,'participation_hash':digest({'document':part.document,'provenance':part.provenance,'lineup':part.lineup}) if part else None,
            'action_id':str(action.id) if action else None,'action_hash':digest({'document':action.document,'provenance':action.provenance,'canonical_actions':action.canonical_actions}) if action else None,
            'analysis_run_id':str(run.id) if run else None,'analysis_hash':digest({'content_hash':run.content_hash,'revision':run.revision,'side_map':run.side_map}) if run else None}
        if scope=='private':item['match_revision']=match.revision
        else:item['publication_revision']=pub.revision if pub else 0
        selected.append((match,protocol,part,action,run,metrics));manifest.append(item)
    return selected,manifest


def _category_complete(document,category,pid,ranges):
    if ranges is None:return False
    declarations=document.get('completeness',{}).get(category,[]);covered=[]
    for d in declarations:
        if d['status']=='complete' and (d.get('player_ids') is None or pid in d['player_ids']):covered.extend([[0,document['duration_ms']]] if d.get('intervals') is None else d['intervals'])
    return duration_s(intersection(ranges,intervals(covered)))==duration_s(ranges)


def _official(protocol,clock,manual=None,links=None):
    offsets={};cursor=0;rules=protocol['regulation']['rules']
    for index,seconds in enumerate(rules['periods_s']+(rules['extra']['periods_s'] if rules['extra']['enabled'] else []),1):offsets[str(index)]=cursor;cursor+=seconds*1000
    return canonical_actions({**protocol['protocol'],'clock_basis':clock,'period_offsets_ms':offsets},manual or [],links or [])



def _without_superseded_video(snapshot,clock,action):
    """Remove only dependent facts; independent manual annotations remain usable."""
    raw=action.document['actions']
    removed={a['id'] for a in raw if a.get('source_episode_id') and a.get('decision')!='rejected'}
    while True:
        dependents={a['id'] for a in raw if a.get('shot_id') in removed}
        if dependents<=removed:break
        removed|=dependents
    affected={'shot':'shots','goal_candidate':'shots','pass':'passes','carry':'carries','duel':'duels','recovery':'recoveries',
        'shot_block':'shot_blocks','turnover':'turnovers','save':'saves','distribution':'distribution','error':'errors'}
    categories={affected[a['kind']] for a in raw if a['id'] in removed}
    safe=[{**a,'clock_basis':clock,'source_refs':[{'kind':'manual','id':a['id'],'version_id':str(action.id)}]} for a in raw if a['id'] not in removed]
    links=[l for l in action.document['links'] if l['source_event_id'] not in removed and l['canonical_event_id'] not in removed]
    return _official(snapshot,clock,safe,links),categories

def performances(db,tid,selected,settings,scope):
    result=[];details={}
    for match,protocol,part,action,run,metrics in selected:
        snapshot=protocol.snapshot if protocol else get_match_view(db,match.id)
        if match.status=='cancelled' or snapshot['status']!='ended' or snapshot['protocol']['result_type']!='played':continue
        reasons=[];pd=part.document if part else None;auto=is_auto(part)
        part_valid=bool(part and pd['time_basis']==settings['time_basis'] and (part.source_protocol_version_id==protocol.id if protocol else False))
        if part_valid and pd['clock_basis']=='video' and (run is None or part.source_analysis_run_id!=run.id):
            part_valid=False;reasons.append('superseded_video_source')
        if not part_valid:reasons.append('missing_or_incompatible_participation')
        full=bool(part_valid and pd['analysis_scope']=='full_match')
        if not full:reasons.append('unknown_full_match_participation')
        clock=pd['clock_basis'] if part_valid else 'game'
        action_valid=bool(action and part_valid and action.source_participation_version_id==part.id and action.source_protocol_version_id==protocol.id and
            action.document['clock_basis']==clock and action.document['duration_ms']==pd['duration_ms'])
        if not action_valid:reasons.append('missing_or_incompatible_action_version')
        if scope=='public':
            source_ids={x.source_analysis_run_id for x in (part,action) if x and x.source_analysis_run_id}
            if source_ids and source_ids!={match.published_analysis_run_id}:action_valid=False;full=False;reasons.append('unpublished_video_source')
        actions=deepcopy(action.canonical_actions) if action_valid else _official(snapshot,clock)
        superseded_categories=set()
        if scope=='private' and action_valid and any(a.get('source_episode_id') and a.get('decision')!='rejected' for a in action.document['actions']) and (run is None or action.source_analysis_run_id!=run.id):
            actions,superseded_categories=_without_superseded_video(snapshot,clock,action)
            reasons.append('superseded_video_source')
        pview=participation_view(part) if part_valid else None
        duration=pd['duration_ms'] if part_valid else sum(snapshot['regulation']['rules']['periods_s'])*1000
        people={p['player_id']:p for p in pd['players']} if part_valid else {}
        for person in snapshot['lineup']:
            pid=person['player_id'];presence=people.get(pid);side=person['side'];team=snapshot[side]['team']
            if presence and presence.get('appeared') is False:continue
            exposure=pview['exposures'].get(pid) if pview else None
            if not exposure:exposure={'unknown':{'eligible_play_s':None,'on_pitch_s':None,'possession_s':None,'without_possession_s':None}}
            known_roles={k for k,v in exposure.items() if k!='unknown' and (v.get('on_pitch_s') or 0)>0}
            single_role=len(known_roles)==1 and not (exposure.get('unknown',{}).get('on_pitch_s') or 0)
            for role,e in exposure.items():
                if e.get('on_pitch_s')==0:continue
                if presence and presence.get('presence') is not None:
                    spans=next((r['intervals'] for r in presence['roles'] if r['role']==role),None)
                    if spans is None:spans=_remaining(intervals(presence['presence']),intervals([pair for r in presence['roles'] for pair in r['intervals']]))
                else:spans=[[0,duration]]
                spans=intervals(spans)
                play=spans if part_valid and pd['time_basis'] in ('running_clock','official_clean') else intersection(spans,intervals(pd['play_intervals'])) if part_valid and pd['play_intervals'] is not None else spans
                categories={key:value for key,value in snapshot['protocol']['completeness'].items() if key in ('goals','assists','fouls','cards')} if protocol else {}
                if action_valid:
                    for category in action.document['completeness']:
                        categories[category]='complete' if full and action.document['analysis_scope']=='full_match' and _category_complete(action.document,category,pid,play) else 'partial'
                for category in superseded_categories:categories[category]='unknown'
                # No physical time is substituted for participation; explicit manual
                # ranges can remain valid despite an additional partial video.
                eligible=e.get('eligible_play_s') if full else None
                participated=e.get('on_pitch_s') if full else None
                covered=1 if eligible is not None and role!='unknown' else 0 if participated is not None else None
                # Автоматическое участие — видео с подтверждённым сопоставлением игроков: та же методика, что для проверенного видео.
                provenance={'side':side,'clock_basis':clock,'analysis_scope':'full_match' if full else 'unknown','source_kind':'reviewed_video' if auto and part_valid else 'manual_verified',
                    'categories':categories,'role_intervals':spans,'eligible_intervals':play,'single_role':single_role or role=='unknown' and not known_roles,
                    'presence_verified':bool(full and presence and presence.get('completeness')=='complete'),
                    'pitch':action.provenance.get('pitch') if action_valid else (snapshot.get('hall_snapshot') or {}),
                    'possession_s':e.get('possession_s') if full else None,'without_possession_s':e.get('without_possession_s') if full else None,
                    'profile_id':settings['profile_id'],'level':settings['level'],'played_at':snapshot['scheduled_at'],
                    'source_version':{'participation':str(part.id) if part else None,'actions':str(action.id) if action else None,'protocol':str(protocol.id) if protocol else None}}
                row=MatchPerformance(str(tid),str(match.id),pid,role,settings['time_basis'],eligible,participated,covered,{},provenance)
                row=replace(row,facts=build_features(row,actions,profile_id=settings['profile_id']))
                moments=[]
                for a in actions:
                    if a.get('player_id')!=pid:continue
                    time=a.get('start_ms')
                    if time is not None and not any(a0<=time<b0 for a0,b0 in spans):continue
                    if time is None and not provenance['single_role']:continue
                    moment={k:a.get(k) for k in ('id','kind','player_id','role','start_ms','end_ms','clock_basis','success','outcome','penalty_conceded','own_goal','counts_as_player_goal','non_penalty_goal')}
                    moment['role']=role;moment['verified']=True
                    if scope=='private':moment['source_refs']=a['source_refs']
                    moments.append(moment)
                physical={k:v for k,v in metrics.get((run.id,pid),{}).items() if k in ('distance_m','observed_s','hsr_m','sprints','vmax_ms','m_per_min')} if run else {}
                details[(row.match_id,pid,role)]={'display_name':person['display_name'],'team_id':str(team['id']),'team_name':team['name'],
                    'stage_label':snapshot.get('stage_label'),'scheduled_at':snapshot['scheduled_at'],'status':snapshot['status'],'result_type':snapshot['protocol']['result_type'],
                    'appeared':presence.get('appeared') if presence else None,'selected_source':digest(provenance['source_version']),
                    'moments':moments,'physical':physical,'reasons':list(reasons),'source':'cv_auto' if auto and part_valid else 'manual'}
                result.append(row)
    return result,details
