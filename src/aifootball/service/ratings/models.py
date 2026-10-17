from sqlalchemy import Column,Uuid,Integer,String,ForeignKey,UniqueConstraint,CheckConstraint,Index,DateTime,text
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base,Entity


class ParticipationVersion(Entity,Base):
    __tablename__='participation_versions'
    match_id=Column(Uuid,ForeignKey('matches.id'),nullable=False)
    revision=Column(Integer,nullable=False)
    status=Column(String(20),nullable=False)
    created_by=Column(Uuid,ForeignKey('admins.id'),nullable=False)
    source_analysis_run_id=Column(Uuid,ForeignKey('analysis_runs.id'))
    source_protocol_version_id=Column(Uuid,ForeignKey('protocol_versions.id'))
    context_hash=Column(String(64),nullable=False)
    document=Column(JSONB,nullable=False)
    provenance=Column(JSONB,nullable=False)
    lineup=Column(JSONB,nullable=False)
    __table_args__=(UniqueConstraint('match_id','revision',name='uq_participation_match_revision'),
        CheckConstraint("status IN ('review','confirmed') AND revision>0",name='ck_participation_status_revision'),
        Index('ix_participation_match_status','match_id','status','revision'))


class ActionVersion(Entity,Base):
    __tablename__='performance_action_versions'
    match_id=Column(Uuid,ForeignKey('matches.id'),nullable=False)
    revision=Column(Integer,nullable=False)
    status=Column(String(20),nullable=False)
    created_by=Column(Uuid,ForeignKey('admins.id'),nullable=False)
    source_participation_version_id=Column(Uuid,ForeignKey('participation_versions.id'))
    source_analysis_run_id=Column(Uuid,ForeignKey('analysis_runs.id'))
    source_protocol_version_id=Column(Uuid,ForeignKey('protocol_versions.id'))
    context_hash=Column(String(64),nullable=False)
    document=Column(JSONB,nullable=False)
    provenance=Column(JSONB,nullable=False)
    lineup=Column(JSONB,nullable=False)
    canonical_actions=Column(JSONB,nullable=False)
    __table_args__=(UniqueConstraint('match_id','revision',name='uq_action_match_revision'),
        CheckConstraint("status IN ('review','confirmed') AND revision>0",name='ck_action_status_revision'),
        Index('ix_action_match_status','match_id','status','revision'))


class RatingPolicyVersion(Entity,Base):
    __tablename__='rating_policy_versions'
    content_hash=Column(String(64),nullable=False,unique=True)
    document=Column(JSONB,nullable=False)


class RatingReferenceVersion(Entity,Base):
    __tablename__='rating_reference_versions'
    tournament_id=Column(Uuid,ForeignKey('tournaments.id'),nullable=False)
    policy_id=Column(Uuid,ForeignKey('rating_policy_versions.id'),nullable=False)
    scope=Column(String(10),nullable=False)
    content_hash=Column(String(64),nullable=False)
    document=Column(JSONB,nullable=False)
    __table_args__=(UniqueConstraint('tournament_id','scope','content_hash',name='uq_rating_reference_content'),)


class TournamentRatingSnapshot(Entity,Base):
    __tablename__='tournament_rating_snapshots'
    tournament_id=Column(Uuid,ForeignKey('tournaments.id'),nullable=False,index=True)
    policy_id=Column(Uuid,ForeignKey('rating_policy_versions.id'),nullable=False)
    reference_id=Column(Uuid,ForeignKey('rating_reference_versions.id'),nullable=False)
    created_by=Column(Uuid,ForeignKey('admins.id'),nullable=False)
    scope=Column(String(10),nullable=False)
    source_fingerprint=Column(String(64),nullable=False)
    inputs=Column(JSONB,nullable=False)
    settings=Column(JSONB,nullable=False)
    summary=Column(JSONB,nullable=False)
    published_at=Column(DateTime(timezone=True))
    __table_args__=(CheckConstraint("scope IN ('private','public')",name='ck_rating_snapshot_scope'),)


class PlayerRatingRow(Entity,Base):
    __tablename__='player_rating_rows'
    snapshot_id=Column(Uuid,ForeignKey('tournament_rating_snapshots.id'),nullable=False)
    player_id=Column(Uuid,ForeignKey('players.id'),nullable=False)
    match_id=Column(Uuid,ForeignKey('matches.id'))
    role=Column(String(20),nullable=False)
    payload=Column(JSONB,nullable=False)
    __table_args__=(Index('uq_rating_match_player_role','snapshot_id','match_id','player_id','role',unique=True,postgresql_where=text('match_id IS NOT NULL')),
        Index('uq_rating_player_summary','snapshot_id','player_id','role',unique=True,postgresql_where=text('match_id IS NULL')),
        Index('ix_rating_snapshot_role_player','snapshot_id','role','player_id'),Index('ix_rating_player_history','player_id','snapshot_id'))


class TournamentRatingState(Entity,Base):
    __tablename__='tournament_rating_states'
    tournament_id=Column(Uuid,ForeignKey('tournaments.id'),nullable=False,unique=True)
    revision=Column(Integer,nullable=False,default=0)
    private_snapshot_id=Column(Uuid,ForeignKey('tournament_rating_snapshots.id'))
    public_snapshot_id=Column(Uuid,ForeignKey('tournament_rating_snapshots.id'))
    public_policy_id=Column(Uuid,ForeignKey('rating_policy_versions.id'))


class RatingMatchPublication(Entity,Base):
    __tablename__='rating_match_publications'
    match_id=Column(Uuid,ForeignKey('matches.id'),nullable=False,unique=True)
    participation_version_id=Column(Uuid,ForeignKey('participation_versions.id'))
    action_version_id=Column(Uuid,ForeignKey('performance_action_versions.id'))
    revision=Column(Integer,nullable=False,default=0)
    created_by=Column(Uuid,ForeignKey('admins.id'),nullable=False)


class RatingCommand(Entity,Base):
    __tablename__='rating_commands'
    tournament_id=Column(Uuid,ForeignKey('tournaments.id'),nullable=False)
    actor_id=Column(Uuid,ForeignKey('admins.id'),nullable=False)
    request_id=Column(Uuid,nullable=False)
    request_hash=Column(String(64),nullable=False)
    response=Column(JSONB,nullable=False)
    __table_args__=(UniqueConstraint('tournament_id','request_id',name='uq_rating_command_request'),)


AUTO_SOURCE='cv_auto'


def is_auto(version):
    """Версия участия или действий создана автоматически из подтверждённого видеоанализа."""
    return version is not None and (version.provenance or {}).get('source_kind')==AUTO_SOURCE
