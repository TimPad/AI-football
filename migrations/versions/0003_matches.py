from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0003_matches'
down_revision='0002_tournaments'


def base(name,*cols):
    op.create_table(name,sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),*cols)


def fk(name,target,label): return sa.Column(name,sa.Uuid(),sa.ForeignKey(target,name=label),nullable=False)


def upgrade():
    for name in ['teams','players']:
        base(name,sa.Column('name',sa.String(200),nullable=False),sa.Column('archived',sa.Boolean(),nullable=False))
    base('entries',fk('tournament_id','tournaments.id','fk_entry_tournament'),fk('team_id','teams.id','fk_entry_team'),
         sa.Column('revision',sa.Integer(),nullable=False),sa.UniqueConstraint('tournament_id','team_id',name='uq_entry_team'))
    base('entry_players',fk('entry_id','entries.id','fk_entry_player_entry'),fk('player_id','players.id','fk_entry_player_player'),
         sa.Column('shirt_number',sa.String(10)),sa.Column('active',sa.Boolean(),nullable=False),
         sa.UniqueConstraint('entry_id','player_id',name='uq_entry_player'))
    op.create_index('uq_active_shirt_number','entry_players',['entry_id','shirt_number'],unique=True,postgresql_where=sa.text('active'))
    base('matches',fk('tournament_id','tournaments.id','fk_match_tournament'),fk('home_entry_id','entries.id','fk_match_home'),
         fk('away_entry_id','entries.id','fk_match_away'),fk('regulation_id','regulations.id','fk_match_regulation'),
         sa.Column('regulation_override',JSONB()),sa.Column('override_reason',sa.String()),
         sa.Column('scheduled_at',sa.DateTime(timezone=True),nullable=False),sa.Column('venue_label',sa.String(200),nullable=False),
         sa.Column('referees',JSONB(),nullable=False),sa.Column('status',sa.String(20),nullable=False),
         sa.Column('revision',sa.Integer(),nullable=False),sa.Column('protocol',JSONB(),nullable=False),
         sa.Column('clock',JSONB(),nullable=False),sa.Column('published_version_id',sa.Uuid()),
         sa.CheckConstraint('home_entry_id != away_entry_id',name='ck_match_different_teams'))
    base('lineup_members',fk('match_id','matches.id','fk_lineup_match'),fk('entry_player_id','entry_players.id','fk_lineup_entry_player'),
         fk('player_id','players.id','fk_lineup_player'),sa.Column('side',sa.String(10),nullable=False),
         sa.Column('shirt_number',sa.String(10)),sa.Column('display_name',sa.String(200),nullable=False),
         sa.UniqueConstraint('match_id','player_id',name='uq_lineup_player'))
    base('match_commands',fk('match_id','matches.id','fk_command_match'),fk('actor_id','admins.id','fk_command_actor'),
         sa.Column('request_id',sa.Uuid(),nullable=False),sa.Column('request_hash',sa.String(64),nullable=False),
         sa.Column('before_revision',sa.Integer(),nullable=False),sa.Column('after_revision',sa.Integer(),nullable=False),
         sa.Column('body',JSONB(),nullable=False),sa.Column('response',JSONB(),nullable=False),
         sa.UniqueConstraint('match_id','request_id',name='uq_command_request'))


def downgrade():
    for name in ['match_commands','lineup_members','matches','entry_players','entries','players','teams']: op.drop_table(name)
