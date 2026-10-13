from copy import deepcopy
from uuid import uuid4
from pydantic import TypeAdapter
from sqlalchemy import select,func
from aifootball.service.common import get_entity
from aifootball.service.db import utcnow
from aifootball.service.errors import DomainError
from aifootball.service.protocol import payloads
from aifootball.service.protocol.schemas import ProtocolDocument
from aifootball.service.protocol.events import validate_event
from aifootball.service.protocol.projection import project_protocol
from aifootball.service.protocol.validation import validate_confirmation
from aifootball.service.protocol.models import ProtocolVersion,Attachment
from aifootball.service.tournaments.models import RegulationVersion
from aifootball.service.tournaments.rules import resolve_rules
from aifootball.service.matches.models import LineupMember
from aifootball.service.matches.operations import get_match_view
from aifootball.service.common import as_dict


def apply_protocol_mutation(db,match,command,actor):
    from aifootball.service.protocol.commands import validate_payload
    doc=ProtocolDocument.model_validate(match.protocol)
    rules=resolve_rules(match,get_entity(db,RegulationVersion,match.regulation_id))
    kind=command.kind
    if kind in ['add_event','replace_event']:
        data=validate_payload(payloads.EventChange,command.payload)
        changing=[data.event,*data.related_events]
        if len({e.id for e in changing})!=len(changing): raise DomainError('duplicate_event','Событие повторяется')
        if data.related_events:
            ids={getattr(e,'penalty_id',None) for e in changing if e.kind in ['goal','penalty_attempt']}
            award_ids={e.id for e in changing if e.kind=='penalty_awarded'}
            if any(e.kind not in ['goal','penalty_attempt','penalty_awarded'] for e in changing) or len(ids|award_ids)!=1 or None in ids:
                raise DomainError('related_event','Связанные события должны относиться к одному пенальти')
        by_id={e.id:e for e in doc.events}
        for e in changing:
            old=by_id.get(e.id)
            if kind=='add_event' and old: raise DomainError('duplicate_event','Событие уже существует',status=409)
            if kind=='replace_event' and not old: raise DomainError('not_found','Событие не найдено',status=404)
            e.created_at=old.created_at if old else utcnow()
        if kind=='add_event': doc.events.extend(changing)
        else:
            replacements={e.id:e for e in changing}
            doc.events=[replacements.get(e.id,e) for e in doc.events]
    elif kind=='remove_event':
        data=validate_payload(payloads.EventRemove,command.payload); ids={data.event_id,*data.related_ids}
        selected=[e for e in doc.events if e.id in ids]
        if len(selected)!=len(ids): raise DomainError('not_found','Событие не найдено',status=404)
        if data.related_ids:
            links={getattr(e,'penalty_id',None) or e.id for e in selected}
            if len(links)!=1 or any(e.kind not in ['goal','penalty_attempt','penalty_awarded'] for e in selected):
                raise DomainError('related_event','Отмена связанного эпизода допустима только для одного пенальти')
        doc.events=[e for e in doc.events if e.id not in ids]
    elif kind=='set_totals':
        data=validate_payload(payloads.SetTotals,command.payload)
        for key in data.model_fields_set:
            value=getattr(data,key)
            if value is None and key!='technical_reason': raise DomainError('validation','Не очищайте раздел целиком; используйте null в неизвестных итогах')
            setattr(doc,key,value)
    elif kind=='set_completeness':
        data=validate_payload(payloads.CompletenessPatch,command.payload)
        for key in data.model_fields_set:
            value=getattr(data,key)
            if value is None: raise DomainError('validation','Выберите степень заполнения')
            setattr(doc.completeness,key,value)
    elif kind=='set_notes':
        data=validate_payload(payloads.Notes,command.payload)
        for key in data.model_fields_set:
            value=getattr(data,key)
            if value is None: raise DomainError('validation','Используйте пустой текст вместо null')
            setattr(doc,key,value)
    elif kind=='confirm':
        data=validate_payload(payloads.Confirm,command.payload)
        if match.status!='ended' or match.clock['phase']=='running':
            raise DomainError('confirmation','Завершите матч и остановите ручные часы')
        projection=project_protocol(doc,rules)
        if doc.completeness.lineup=='complete':
            counts={s:db.scalar(select(func.count()).select_from(LineupMember).where(LineupMember.match_id==match.id,LineupMember.side==s)) for s in ['home','away']}
            if any(n<rules.players_on_pitch for n in counts.values()):
                projection.incomplete_sections=list(set(projection.incomplete_sections)|{'lineup'})
        validate_confirmation(doc,projection,acknowledge_incomplete=data.acknowledge_incomplete)
        if not rules.allow_draw and projection.effective_score['home']==projection.effective_score['away']:
            if not rules.shootout.enabled or any(v is None for v in doc.shootout_totals.model_dump().values()) or doc.shootout_totals.home==doc.shootout_totals.away:
                raise DomainError('winner','Регламент требует определить победителя; укажите итог серии пенальти')
        for side in ['home','away']:
            reported=getattr(doc.reported_totals,side)
            if any(p<1 or p>len(rules.periods_s)+(len(rules.extra.periods_s) if rules.extra.enabled else 0) for p in reported.period_scores):
                raise DomainError('period_scores','Счёт указан для несуществующего периода')
        doc.draft=False; match.protocol=doc.model_dump(mode='json'); db.flush()
        number=(db.scalar(select(func.max(ProtocolVersion.number)).where(ProtocolVersion.match_id==match.id)) or 0)+1
        snapshot=get_match_view(db,match.id)
        snapshot['projection']['incomplete_sections']=projection.incomplete_sections
        snapshot['protocol']['draft']=False
        db.add(ProtocolVersion(match_id=match.id,number=number,snapshot=snapshot,confirmed_by=actor.id))
    elif kind=='reopen':
        validate_payload(payloads.Empty,command.payload)
        latest=db.scalar(select(ProtocolVersion).where(ProtocolVersion.match_id==match.id).order_by(ProtocolVersion.number.desc()))
        if doc.draft or latest is None: raise DomainError('draft','Протокол уже редактируется')
        doc=ProtocolDocument.model_validate(deepcopy(latest.snapshot['protocol'])); doc.draft=True
    elif kind=='publish':
        data=validate_payload(payloads.Publish,command.payload); version=get_entity(db,ProtocolVersion,data.version_id)
        if version.match_id!=match.id: raise DomainError('foreign_version','Версия другого матча')
        version.public_id=version.public_id or uuid4(); version.published_at=utcnow(); match.published_version_id=version.id
    elif kind=='unpublish':
        validate_payload(payloads.Empty,command.payload); match.published_version_id=None
    elif kind in ['add_attachment','remove_attachment']:
        data=validate_payload(payloads.AttachmentPayload,command.payload); attachment=get_entity(db,Attachment,data.attachment_id)
        if attachment.match_id!=match.id: raise DomainError('foreign_attachment','Документ другого матча')
        if kind=='add_attachment':
            if attachment.id in doc.attachment_ids: raise DomainError('duplicate_attachment','Документ уже прикреплён')
            if attachment.removed_at: raise DomainError('removed_attachment','Документ удалён из протокола')
            doc.attachment_ids.append(attachment.id)
        else:
            if attachment.id not in doc.attachment_ids: raise DomainError('not_found','Документ не найден',status=404)
            doc.attachment_ids.remove(attachment.id); attachment.removed_at=utcnow()
    else:
        raise DomainError('command','Неизвестная команда изменения протокола')
    lineup=[as_dict(row) for row in db.scalars(select(LineupMember).where(LineupMember.match_id==match.id))]
    for e in doc.events: validate_event(e,regulation=rules,lineup=lineup,events=doc.events)
    match.protocol=doc.model_dump(mode='json')
