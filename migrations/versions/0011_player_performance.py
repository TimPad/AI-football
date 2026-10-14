"""Immutable participation/role snapshots; never inferred from CV visibility."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='0011_player_performance'
down_revision='0010_match_understanding'


def upgrade():
    op.create_table('participation_versions',
        sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('match_id',sa.Uuid(),sa.ForeignKey('matches.id'),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('status',sa.String(20),nullable=False),
        sa.Column('created_by',sa.Uuid(),sa.ForeignKey('admins.id'),nullable=False),
        sa.Column('source_analysis_run_id',sa.Uuid(),sa.ForeignKey('analysis_runs.id')),
        sa.Column('source_protocol_version_id',sa.Uuid(),sa.ForeignKey('protocol_versions.id')),
        sa.Column('context_hash',sa.String(64),nullable=False),sa.Column('document',postgresql.JSONB(),nullable=False),
        sa.Column('provenance',postgresql.JSONB(),nullable=False),sa.Column('lineup',postgresql.JSONB(),nullable=False),
        sa.UniqueConstraint('match_id','revision',name='uq_participation_match_revision'),
        sa.CheckConstraint("status IN ('review','confirmed') AND revision>0",name='ck_participation_status_revision'))
    op.create_index('ix_participation_match_status','participation_versions',['match_id','status','revision'])


def downgrade():op.drop_table('participation_versions')
