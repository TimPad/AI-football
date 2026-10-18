"""Bind an unverified registration's credentials to its email proof."""
from alembic import op
import sqlalchemy as sa
revision='0026_registration_credentials'
down_revision='0025_analysis_queue_indexes'
def upgrade():
    op.add_column('captain_tokens',sa.Column('registration_password_hash',sa.String(),nullable=True))
    op.add_column('captain_tokens',sa.Column('registration_display_name',sa.String(200),nullable=True))
    op.create_index('ix_analysis_run_match_created','analysis_runs',['match_id','created_at','id'])
def downgrade():
    op.drop_index('ix_analysis_run_match_created',table_name='analysis_runs')
    op.drop_column('captain_tokens','registration_display_name')
    op.drop_column('captain_tokens','registration_password_hash')
