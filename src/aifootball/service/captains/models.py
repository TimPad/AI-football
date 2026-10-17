from sqlalchemy import Column,String,Boolean,Integer,BigInteger,Uuid,ForeignKey,DateTime,Index,text,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base,Entity

class CaptainAccount(Entity,Base):
    __tablename__='captain_accounts'
    email=Column(String(254),nullable=False,unique=True)
    display_name=Column(String(200),nullable=False)
    password_hash=Column(String,nullable=False)
    verified_at=Column(DateTime(timezone=True))
    active=Column(Boolean,nullable=False,default=True)
    security_revision=Column(Integer,nullable=False,default=0)

class CaptainSession(Base):
    __tablename__='captain_sessions'
    token_hash=Column(String(64),primary_key=True)
    account_id=Column(Uuid,ForeignKey('captain_accounts.id'),nullable=False)
    csrf_token=Column(String(100),nullable=False)
    expires_at=Column(DateTime(timezone=True),nullable=False)

class CaptainToken(Entity,Base):
    __tablename__='captain_tokens'
    account_id=Column(Uuid,ForeignKey('captain_accounts.id'),nullable=False)
    purpose=Column(String(20),nullable=False)
    token_hash=Column(String(64),nullable=False,unique=True)
    security_revision=Column(Integer,nullable=False)
    expires_at=Column(DateTime(timezone=True),nullable=False)
    used_at=Column(DateTime(timezone=True))
    used_request_id=Column(Uuid)
    used_hash=Column(String(64))

class CaptainRateLimit(Base):
    __tablename__='captain_rate_limits'
    key=Column(String(64),primary_key=True)
    window=Column(BigInteger,nullable=False)
    count=Column(Integer,nullable=False)

class CaptainAuthCommand(Base):
    __tablename__='captain_auth_commands'
    request_id=Column(Uuid,primary_key=True)
    request_hash=Column(String(64),nullable=False)
    response=Column(JSONB,nullable=False)

class MailOutbox(Entity,Base):
    __tablename__='mail_outbox'
    kind=Column(String(30),nullable=False)
    encrypted_payload=Column(String)
    expires_at=Column(DateTime(timezone=True),nullable=False)
    sent_at=Column(DateTime(timezone=True))
    next_attempt_at=Column(DateTime(timezone=True),nullable=False)
    attempts=Column(Integer,nullable=False,default=0)
    error_code=Column(String(40))

class TeamCaptainGrant(Entity,Base):
    __tablename__='team_captain_grants'
    account_id=Column(Uuid,ForeignKey('captain_accounts.id'),nullable=False)
    team_id=Column(Uuid,ForeignKey('teams.id'),nullable=False)
    active=Column(Boolean,nullable=False,default=True)
    __table_args__=(Index('uq_team_active_captain','team_id',unique=True,postgresql_where=text('active')),)

class CaptainGrantAudit(Entity,Base):
    __tablename__='captain_grant_audits'
    grant_id=Column(Uuid,ForeignKey('team_captain_grants.id'),nullable=False)
    actor_id=Column(Uuid,ForeignKey('admins.id'),nullable=False)
    action=Column(String(20),nullable=False)
    reason=Column(String(1000),nullable=False)

class TeamCaptainInvitation(Entity,Base):
    __tablename__='team_captain_invitations'
    team_id=Column(Uuid,ForeignKey('teams.id'),nullable=False)
    email=Column(String(254),nullable=False)
    token_hash=Column(String(64),nullable=False,unique=True)
    expires_at=Column(DateTime(timezone=True),nullable=False)
    used_at=Column(DateTime(timezone=True))
    revoked_at=Column(DateTime(timezone=True))
    created_by=Column(Uuid,ForeignKey('admins.id'),nullable=False)

class CaptainOwnershipRequest(Entity,Base):
    __tablename__='captain_ownership_requests'
    account_id=Column(Uuid,ForeignKey('captain_accounts.id'),nullable=False)
    team_id=Column(Uuid,ForeignKey('teams.id'),nullable=False)
    message=Column(String(1000),nullable=False)
    status=Column(String(20),nullable=False,default='pending')

class CaptainCommand(Entity,Base):
    __tablename__='captain_commands'
    actor_id=Column(Uuid,ForeignKey('captain_accounts.id'),nullable=False)
    request_id=Column(Uuid,nullable=False,unique=True)
    kind=Column(String(50),nullable=False)
    request_hash=Column(String(64),nullable=False)
    response=Column(JSONB,nullable=False)

class CaptainImage(Base):
    __tablename__='captain_images'
    image_id=Column(Uuid,ForeignKey('catalog_images.id'),primary_key=True)
    account_id=Column(Uuid,ForeignKey('captain_accounts.id'),nullable=False)

class PlayerProfileProposal(Entity,Base):
    __tablename__='player_profile_proposals'
    account_id=Column(Uuid,ForeignKey('captain_accounts.id'),nullable=False)
    team_id=Column(Uuid,ForeignKey('teams.id'),nullable=False)
    player_id=Column(Uuid,ForeignKey('players.id'))
    expected_player_revision=Column(Integer)
    payload=Column(JSONB,nullable=False)
    status=Column(String(30),nullable=False,default='pending')

class EntrySubmission(Entity,Base):
    __tablename__='entry_submissions'
    tournament_id=Column(Uuid,ForeignKey('tournaments.id'),nullable=False)
    team_id=Column(Uuid,ForeignKey('teams.id'),nullable=False)
    created_by=Column(Uuid,ForeignKey('captain_accounts.id'),nullable=False)
    revision=Column(Integer,nullable=False,default=0)
    status=Column(String(30),nullable=False,default='draft')
    draft=Column(JSONB,nullable=False)
    submitted_version_id=Column(Uuid)
    accepted_version_id=Column(Uuid)
    reason=Column(String(1000),nullable=False,default='')
    __table_args__=(UniqueConstraint('tournament_id','team_id',name='uq_entry_submission_team'),)

class EntrySubmissionVersion(Entity,Base):
    __tablename__='entry_submission_versions'
    submission_id=Column(Uuid,ForeignKey('entry_submissions.id'),nullable=False)
    actor_id=Column(Uuid,ForeignKey('captain_accounts.id'),nullable=False)
    number=Column(Integer,nullable=False)
    payload=Column(JSONB,nullable=False)
    __table_args__=(UniqueConstraint('submission_id','number',name='uq_entry_submission_version'),)

class EntryInvitation(Entity,Base):
    __tablename__='entry_invitations'
    tournament_id=Column(Uuid,ForeignKey('tournaments.id'),nullable=False)
    team_id=Column(Uuid,ForeignKey('teams.id'),nullable=False)
    created_by=Column(Uuid,ForeignKey('admins.id'),nullable=False)
    active=Column(Boolean,nullable=False,default=True)
    __table_args__=(Index('uq_active_entry_invitation','tournament_id','team_id',unique=True,postgresql_where=text('active')),)
