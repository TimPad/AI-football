from sqlalchemy import Column,String,Boolean,Integer,Uuid,ForeignKey,UniqueConstraint,Index,text,Date,Float
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base,Entity


class Team(Entity,Base):
    __tablename__='teams'
    name=Column(String(200),nullable=False)
    archived=Column(Boolean,nullable=False,default=False)
    revision=Column(Integer,nullable=False,default=0)
    description=Column(String(4000),nullable=False,default='')
    logo_id=Column(Uuid,ForeignKey('catalog_images.id',name='fk_team_logo'))


class Player(Entity,Base):
    __tablename__='players'
    name=Column(String(200),nullable=False)
    archived=Column(Boolean,nullable=False,default=False)
    revision=Column(Integer,nullable=False,default=0)
    photo_id=Column(Uuid,ForeignKey('catalog_images.id',name='fk_player_photo'))
    birth_date=Column(Date)
    position=Column(String(30))
    height_cm=Column(Integer)
    weight_kg=Column(Float)


class CatalogImage(Entity,Base):
    __tablename__='catalog_images'
    sha256=Column(String(64),nullable=False)
    size=Column(Integer,nullable=False)


class TeamMember(Entity,Base):
    __tablename__='team_members'
    team_id=Column(Uuid,ForeignKey('teams.id',name='fk_member_team'),nullable=False)
    player_id=Column(Uuid,ForeignKey('players.id',name='fk_member_player'),nullable=False)
    shirt_number=Column(String(10))
    active=Column(Boolean,nullable=False,default=True)
    __table_args__=(UniqueConstraint('team_id','player_id',name='uq_team_member'),
        Index('uq_team_active_number','team_id','shirt_number',unique=True,postgresql_where=text('active')))


class TeamProfileCommand(Entity,Base):
    __tablename__='team_profile_commands'
    team_id=Column(Uuid,ForeignKey('teams.id',name='fk_profile_command_team'),nullable=False)
    request_id=Column(Uuid,nullable=False,unique=True)
    request_hash=Column(String(64),nullable=False)
    response=Column(JSONB,nullable=False)


class Entry(Entity,Base):
    __tablename__='entries'
    tournament_id=Column(Uuid,ForeignKey('tournaments.id',name='fk_entry_tournament'),nullable=False)
    team_id=Column(Uuid,ForeignKey('teams.id',name='fk_entry_team'),nullable=False)
    revision=Column(Integer,nullable=False,default=0)
    __table_args__=(UniqueConstraint('tournament_id','team_id',name='uq_entry_team'),)


class EntryPlayer(Entity,Base):
    __tablename__='entry_players'
    entry_id=Column(Uuid,ForeignKey('entries.id',name='fk_entry_player_entry'),nullable=False)
    player_id=Column(Uuid,ForeignKey('players.id',name='fk_entry_player_player'),nullable=False)
    shirt_number=Column(String(10))
    active=Column(Boolean,nullable=False,default=True)
    __table_args__=(UniqueConstraint('entry_id','player_id',name='uq_entry_player'),
        Index('uq_active_shirt_number','entry_id','shirt_number',unique=True,postgresql_where=text('active')))
