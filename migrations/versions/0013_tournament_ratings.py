"""Immutable ratings, published inputs and independent tournament publication."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0013_tournament_ratings'
down_revision='0012_performance_actions'


def _entity():return [sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False)]
def _fk(name,table,nullable=False):return sa.Column(name,sa.Uuid(),sa.ForeignKey(table+'.id'),nullable=nullable)


def upgrade():
    op.add_column('matches',sa.Column('stage_label',sa.String(100)))
    op.create_table('rating_policy_versions',*_entity(),sa.Column('content_hash',sa.String(64),nullable=False,unique=True),sa.Column('document',JSONB(),nullable=False))
    op.create_table('rating_reference_versions',*_entity(),_fk('tournament_id','tournaments'),_fk('policy_id','rating_policy_versions'),
        sa.Column('scope',sa.String(10),nullable=False),sa.Column('content_hash',sa.String(64),nullable=False),sa.Column('document',JSONB(),nullable=False),
        sa.UniqueConstraint('tournament_id','scope','content_hash',name='uq_rating_reference_content'))
    op.create_table('tournament_rating_snapshots',*_entity(),_fk('tournament_id','tournaments'),_fk('policy_id','rating_policy_versions'),
        _fk('reference_id','rating_reference_versions'),_fk('created_by','admins'),sa.Column('scope',sa.String(10),nullable=False),
        sa.Column('source_fingerprint',sa.String(64),nullable=False),sa.Column('inputs',JSONB(),nullable=False),sa.Column('settings',JSONB(),nullable=False),
        sa.Column('summary',JSONB(),nullable=False),sa.Column('published_at',sa.DateTime(timezone=True)),
        sa.CheckConstraint("scope IN ('private','public')",name='ck_rating_snapshot_scope'))
    op.create_index('ix_tournament_rating_snapshots_tournament_id','tournament_rating_snapshots',['tournament_id'])
    op.create_table('player_rating_rows',*_entity(),_fk('snapshot_id','tournament_rating_snapshots'),_fk('player_id','players'),_fk('match_id','matches',True),
        sa.Column('role',sa.String(20),nullable=False),sa.Column('payload',JSONB(),nullable=False))
    op.create_index('uq_rating_match_player_role','player_rating_rows',['snapshot_id','match_id','player_id','role'],unique=True,postgresql_where=sa.text('match_id IS NOT NULL'))
    op.create_index('uq_rating_player_summary','player_rating_rows',['snapshot_id','player_id','role'],unique=True,postgresql_where=sa.text('match_id IS NULL'))
    op.create_index('ix_rating_snapshot_role_player','player_rating_rows',['snapshot_id','role','player_id'])
    op.create_index('ix_rating_player_history','player_rating_rows',['player_id','snapshot_id'])
    op.create_table('tournament_rating_states',*_entity(),_fk('tournament_id','tournaments'),sa.Column('revision',sa.Integer(),nullable=False),
        _fk('private_snapshot_id','tournament_rating_snapshots',True),_fk('public_snapshot_id','tournament_rating_snapshots',True),_fk('public_policy_id','rating_policy_versions',True),sa.UniqueConstraint('tournament_id'))
    op.create_table('rating_match_publications',*_entity(),_fk('match_id','matches'),_fk('participation_version_id','participation_versions',True),
        _fk('action_version_id','performance_action_versions',True),sa.Column('revision',sa.Integer(),nullable=False),_fk('created_by','admins'),sa.UniqueConstraint('match_id'))
    op.create_table('rating_commands',*_entity(),_fk('tournament_id','tournaments'),_fk('actor_id','admins'),sa.Column('request_id',sa.Uuid(),nullable=False),
        sa.Column('request_hash',sa.String(64),nullable=False),sa.Column('response',JSONB(),nullable=False),sa.UniqueConstraint('tournament_id','request_id',name='uq_rating_command_request'))


def downgrade():
    for table in ('rating_commands','rating_match_publications','tournament_rating_states','player_rating_rows','tournament_rating_snapshots','rating_reference_versions','rating_policy_versions'):op.drop_table(table)
    op.drop_column('matches','stage_label')
