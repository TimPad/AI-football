from sqlalchemy import Column,Uuid,String,Integer,ForeignKey,DateTime,Index,text,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base,Entity

class TeamIdentityReviewTask(Entity,Base):
    __tablename__='team_identity_review_tasks'
    run_id=Column(Uuid,ForeignKey('analysis_runs.id'),nullable=False,index=True)
    team_id=Column(Uuid,ForeignKey('teams.id'),nullable=False,index=True)
    grant_id=Column(Uuid,ForeignKey('team_captain_grants.id'),nullable=False)
    side=Column(String(10),nullable=False)
    created_by=Column(Uuid,ForeignKey('admins.id'),nullable=False)
    context_hash=Column(String(64),nullable=False)
    group_fingerprint=Column(String(64),nullable=False)
    own_assignment_fingerprint=Column(String(64),nullable=False)
    allowed_track_ids=Column(JSONB,nullable=False)
    allowed_player_ids=Column(JSONB,nullable=False)
    groups=Column(JSONB,nullable=False)
    players=Column(JSONB,nullable=False)
    draft=Column(JSONB,nullable=False,default=list)
    status=Column(String(30),nullable=False,default='open')
    revision=Column(Integer,nullable=False,default=0)
    reason=Column(String(1000),nullable=False,default='')
    expires_at=Column(DateTime(timezone=True),nullable=False)
    __table_args__=(Index('uq_open_team_identity_task','run_id','side',unique=True,postgresql_where=text("status IN ('open','needs_material_fix')")),)

class TeamIdentityConfirmation(Entity,Base):
    __tablename__='team_identity_confirmations'
    run_id=Column(Uuid,ForeignKey('analysis_runs.id'),nullable=False,index=True)
    team_id=Column(Uuid,ForeignKey('teams.id'),nullable=False)
    side=Column(String(10),nullable=False)
    version=Column(Integer,nullable=False)
    task_id=Column(Uuid,ForeignKey('team_identity_review_tasks.id'))
    actor_kind=Column(String(10),nullable=False)
    actor_id=Column(Uuid,nullable=False)  # Discriminated actor; never a captain UUID in an admins FK.
    reason=Column(String(1000),nullable=False)
    context_hash=Column(String(64),nullable=False)
    group_fingerprint=Column(String(64),nullable=False)
    assignment_fingerprint=Column(String(64),nullable=False)
    decisions=Column(JSONB,nullable=False)
    __table_args__=(UniqueConstraint('run_id','side','version',name='uq_team_confirmation_version'),)
