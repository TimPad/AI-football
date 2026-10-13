from sqlalchemy import Column,String,Integer,Uuid,ForeignKey,DateTime,UniqueConstraint,CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base,Entity


class Match(Entity,Base):
    __tablename__='matches'
    tournament_id=Column(Uuid,ForeignKey('tournaments.id',name='fk_match_tournament'),nullable=False)
    home_entry_id=Column(Uuid,ForeignKey('entries.id',name='fk_match_home'),nullable=False)
    away_entry_id=Column(Uuid,ForeignKey('entries.id',name='fk_match_away'),nullable=False)
    regulation_id=Column(Uuid,ForeignKey('regulations.id',name='fk_match_regulation'),nullable=False)
    regulation_override=Column(JSONB)
    override_reason=Column(String)
    scheduled_at=Column(DateTime(timezone=True),nullable=False)
    venue_label=Column(String(200),nullable=False,default='')
    referees=Column(JSONB,nullable=False,default=list)
    status=Column(String(20),nullable=False,default='scheduled')
    revision=Column(Integer,nullable=False,default=0)
    protocol=Column(JSONB,nullable=False)
    clock=Column(JSONB,nullable=False)
    published_version_id=Column(Uuid)
    __table_args__=(CheckConstraint('home_entry_id != away_entry_id',name='ck_match_different_teams'),)


class LineupMember(Entity,Base):
    __tablename__='lineup_members'
    match_id=Column(Uuid,ForeignKey('matches.id',name='fk_lineup_match'),nullable=False)
    entry_player_id=Column(Uuid,ForeignKey('entry_players.id',name='fk_lineup_entry_player'),nullable=False)
    player_id=Column(Uuid,ForeignKey('players.id',name='fk_lineup_player'),nullable=False)
    side=Column(String(10),nullable=False)
    shirt_number=Column(String(10))
    display_name=Column(String(200),nullable=False)
    __table_args__=(UniqueConstraint('match_id','player_id',name='uq_lineup_player'),)


class MatchCommand(Entity,Base):
    __tablename__='match_commands'
    match_id=Column(Uuid,ForeignKey('matches.id',name='fk_command_match'),nullable=False)
    actor_id=Column(Uuid,ForeignKey('admins.id',name='fk_command_actor'),nullable=False)
    request_id=Column(Uuid,nullable=False)
    request_hash=Column(String(64),nullable=False)
    before_revision=Column(Integer,nullable=False)
    after_revision=Column(Integer,nullable=False)
    body=Column(JSONB,nullable=False)
    response=Column(JSONB,nullable=False)
    __table_args__=(UniqueConstraint('match_id','request_id',name='uq_command_request'),)
