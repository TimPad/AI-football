from sqlalchemy import Column,String,Boolean,Integer,Uuid,ForeignKey,UniqueConstraint,Index,text
from aifootball.service.db import Base,Entity


class Team(Entity,Base):
    __tablename__='teams'
    name=Column(String(200),nullable=False)
    archived=Column(Boolean,nullable=False,default=False)


class Player(Entity,Base):
    __tablename__='players'
    name=Column(String(200),nullable=False)
    archived=Column(Boolean,nullable=False,default=False)


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
