"""Private match understanding, review history and explicit side confirmation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision='0010_match_understanding'
down_revision='0009_analysis_revision'


def upgrade():
    op.add_column('analysis_runs',sa.Column('understanding',postgresql.JSONB(),nullable=True))
    op.add_column('analysis_runs',sa.Column('understanding_reviews',postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")))
    op.add_column('analysis_runs',sa.Column('side_map_verified',sa.Boolean(),nullable=False,server_default=sa.false()))
    # Before this migration a review revision could only come from explicit assignments.
    op.execute("UPDATE analysis_runs SET side_map_verified=TRUE WHERE status='confirmed' OR revision>0")
    op.create_table('analysis_understanding_decisions',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('run_id',sa.Uuid(),sa.ForeignKey('analysis_runs.id'),nullable=False),
        sa.Column('event_id',sa.String(100),nullable=False),
        sa.Column('actor_id',sa.Uuid(),sa.ForeignKey('admins.id'),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('before',postgresql.JSONB(),nullable=True),
        sa.Column('after',postgresql.JSONB(),nullable=False),
        sa.UniqueConstraint('run_id','revision',name='uq_understanding_run_revision'))
    op.create_index('ix_understanding_run_event','analysis_understanding_decisions',['run_id','event_id'])


def downgrade():
    op.drop_table('analysis_understanding_decisions')
    op.drop_column('analysis_runs','side_map_verified')
    op.drop_column('analysis_runs','understanding_reviews')
    op.drop_column('analysis_runs','understanding')
