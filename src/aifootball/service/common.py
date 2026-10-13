from uuid import UUID
from sqlalchemy import select, func, inspect
from aifootball.service.errors import DomainError


def get_entity(db, cls, entity_id, *, lock=False):
    statement=select(cls).where(cls.id==entity_id)
    if lock: statement=statement.with_for_update()
    entity=db.scalar(statement)
    if entity is None: raise DomainError('not_found','Запись не найдена',status=404)
    return entity


def as_dict(entity):
    return {column.key: getattr(entity,column.key) for column in inspect(type(entity)).columns}


def list_entities(db, cls, *, where=(), limit=50, offset=0, order=None):
    query=select(cls).where(*where)
    query=query.order_by(order if order is not None else cls.created_at.desc(),cls.id).limit(limit).offset(offset)
    total=db.scalar(select(func.count()).select_from(cls).where(*where))
    return {'items':[as_dict(item) for item in db.scalars(query)],'total':total}
