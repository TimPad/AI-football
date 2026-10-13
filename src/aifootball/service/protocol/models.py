from sqlalchemy import Column,Uuid,Integer,String,DateTime,ForeignKey,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base,Entity,utcnow


class ProtocolVersion(Entity,Base):
    __tablename__='protocol_versions'
    match_id=Column(Uuid,ForeignKey('matches.id',name='fk_version_match'),nullable=False)
    number=Column(Integer,nullable=False)
    snapshot=Column(JSONB,nullable=False)
    confirmed_by=Column(Uuid,ForeignKey('admins.id',name='fk_version_admin'),nullable=False)
    confirmed_at=Column(DateTime(timezone=True),nullable=False,default=utcnow)
    published_at=Column(DateTime(timezone=True))
    public_id=Column(Uuid,unique=True)
    __table_args__=(UniqueConstraint('match_id','number',name='uq_protocol_version'),)


class Attachment(Entity,Base):
    __tablename__='attachments'
    match_id=Column(Uuid,ForeignKey('matches.id',name='fk_attachment_match'),nullable=False)
    original_name=Column(String(300),nullable=False)
    storage_key=Column(String(100),nullable=False)
    mime=Column(String(100),nullable=False)
    size=Column(Integer,nullable=False)
    sha256=Column(String(64),nullable=False)
    created_by=Column(Uuid,ForeignKey('admins.id',name='fk_attachment_admin'),nullable=False)
    removed_at=Column(DateTime(timezone=True))
