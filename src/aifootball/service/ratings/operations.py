from copy import deepcopy
from uuid import UUID
from sqlalchemy import select,func
from aifootball.analytics.exchange import canonical
from hashlib import sha256
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.matches.models import Match
from aifootball.service.matches.operations import get_match_view
from aifootball.service.analysis.models import AnalysisRun,AnalysisJob
from aifootball.service.analysis.jobs import prior_command,remember
from aifootball.service.protocol.models import ProtocolVersion
from aifootball.service.ratings.models import ParticipationVersion,is_auto
from aifootball.ratings.validate import validate_participation,exposure_by_role


def participation_view(version):
    doc=deepcopy(version.document);sides={p['player_id']:p['side'] for p in version.lineup}
    exposures={}
    for player in doc['players']:
        side=sides[player['player_id']];opponent='away' if side=='home' else 'home'
        exposures[player['player_id']]=exposure_by_role({**player,'time_basis':doc['time_basis'],
            'opponent_possession_intervals':doc['possession_intervals'][opponent]},
            doc['play_intervals'],doc['possession_intervals'][side])
    return {'id':version.id,'match_id':version.match_id,'revision':version.revision,'status':version.status,'auto':is_auto(version),
        'created_at':version.created_at,'created_by':version.created_by,'context_hash':version.context_hash,
        'document':doc,'lineup':version.lineup,'provenance':version.provenance,'exposures':exposures}


def participation_overview(db,match_id):
    match=get_entity(db,Match,match_id);view=get_match_view(db,match_id)
    versions=list(db.scalars(select(ParticipationVersion).where(ParticipationVersion.match_id==match_id).order_by(ParticipationVersion.revision.desc())))
    runs=[{'id':str(run.id),'created_at':run.created_at,'source_video':run.manifest['source_video']}
          for run in db.scalars(select(AnalysisRun).where(AnalysisRun.match_id==match_id,AnalysisRun.status=='confirmed').order_by(AnalysisRun.created_at.desc()))]
    protocols=[{'id':str(v.id),'number':v.number,'confirmed_at':v.confirmed_at}
        for v in db.scalars(select(ProtocolVersion).where(ProtocolVersion.match_id==match_id).order_by(ProtocolVersion.number.desc()))]
    return {'match_id':match_id,'match_revision':match.revision,'revision':versions[0].revision if versions else 0,
        'current':participation_view(versions[0]) if versions else None,
        'versions':[{'id':v.id,'revision':v.revision,'status':v.status,'created_at':v.created_at,'auto':is_auto(v)} for v in versions],
        'lineup':view['lineup'],'rules':view['regulation']['rules'],'protocol_versions':protocols,'analysis_runs':runs}


def save_participation(db,match_id,actor_id,data,*,source_kind=None):
    payload=data.model_dump(mode='json',exclude={'request_id'})
    old,hashed=prior_command(db,match_id,actor_id,data.request_id,'participation',payload)
    if old:return old.response
    match=get_entity(db,Match,match_id,lock=True)
    latest=db.scalar(select(func.max(ParticipationVersion.revision)).where(ParticipationVersion.match_id==match_id)) or 0
    if data.expected_revision!=latest or data.expected_match_revision!=match.revision:
        raise DomainError('revision_conflict','Участие или протокол изменены; обновите данные',status=409,current_revision=latest)
    doc=data.document.model_dump(mode='json');view=get_match_view(db,match_id)
    rules=view['regulation']['rules'];lineup=[{key:p[key] for key in ('player_id','side','shirt_number','display_name')} for p in view['lineup']]
    source=None;protocol=None
    if doc['source_analysis_run_id'] is not None:
        source=get_entity(db,AnalysisRun,UUID(doc['source_analysis_run_id']))
        if source.match_id!=match_id or source.status!='confirmed':raise DomainError('participation_source','Выберите подтверждённый отчёт этого матча')
    if doc['source_protocol_version_id'] is not None:
        protocol=get_entity(db,ProtocolVersion,UUID(doc['source_protocol_version_id']))
        if protocol.match_id!=match_id:raise DomainError('participation_source','Протокол относится к другому матчу')
        rules=protocol.snapshot['regulation']['rules']
        lineup=[{key:p[key] for key in ('player_id','side','shirt_number','display_name')} for p in protocol.snapshot['lineup']]
    if doc['clock_basis']=='video':
        if source is None or doc['duration_ms']!=round(source.manifest['source_video']['duration_s']*1000):
            raise DomainError('participation_source','Укажите подтверждённую запись и её точную длительность')
        job=get_entity(db,AnalysisJob,source.job_id)
        video_roster={p['player_id']:p['side'] for p in job.context['rosters']}
        selected_roster={p['player_id']:p['side'] for p in lineup}
        if any(video_roster.get(p['player_id'])!=selected_roster.get(p['player_id']) for p in doc['players']):
            raise DomainError('participation_source','Игрок не входит в состав выбранной видеозаписи')
    else:
        maximum=sum(rules['periods_s'])+(sum(rules['extra']['periods_s']) if rules['extra']['enabled'] else 0)
        if doc['duration_ms']>maximum*1000:raise DomainError('participation_time','Время выходит за пределы регламента')
        if doc['analysis_scope']=='full_match' and doc['duration_ms']<sum(rules['periods_s'])*1000:
            raise DomainError('participation_scope','Короткий интервал не является полным матчем')
    if doc['time_basis']=='official_clean' and (doc['clock_basis']!='game' or protocol is None or
        protocol.snapshot['protocol']['completeness']['time']!='complete' or protocol.snapshot['regulation']['rules']['clock_mode']!='clean'):
        raise DomainError('participation_clock','Для чистого времени нужны игровая шкала и подтверждённый полный учёт времени; автоматической привязки к видео нет')
    if doc['time_basis']=='official_clean':
        if doc['play_intervals'] not in (None,[[0,doc['duration_ms']]]):
            raise DomainError('participation_clock','Шкала чистого игрового времени уже исключает остановки')
        doc['play_intervals']=[[0,doc['duration_ms']]]
    try:validate_participation(doc,lineup,players_on_pitch=rules['players_on_pitch'])
    except ValueError as exc:raise DomainError('participation_intervals',str(exc)) from exc
    protocol_doc=protocol.snapshot['protocol'] if protocol else match.protocol
    provenance={'match_revision':match.revision,'protocol_version_id':str(protocol.id) if protocol else None,
        'protocol_sha256':sha256(canonical(protocol_doc)).hexdigest(),'protocol':deepcopy(protocol_doc),
        'regulation':rules,'analysis_run_id':str(source.id) if source else None,'source_kind':source_kind or ('manual_verified' if data.status=='confirmed' else 'manual_draft')}
    fingerprint=sha256(canonical({'lineup':lineup,'provenance':provenance,'clock_basis':doc['clock_basis'],'time_basis':doc['time_basis']})).hexdigest()
    version=ParticipationVersion(match_id=match_id,revision=latest+1,status=data.status,created_by=actor_id,
        source_analysis_run_id=source.id if source else None,source_protocol_version_id=protocol.id if protocol else None,
        context_hash=fingerprint,document=doc,lineup=lineup,provenance=provenance)
    db.add(version);db.flush()
    return remember(db,match_id,actor_id,data.request_id,hashed,participation_view(version))
