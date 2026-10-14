"""Independent revision for active/public analysis pointers."""
from alembic import op
import sqlalchemy as sa

revision = '0009_analysis_revision'
down_revision = '0008_analysis'


def upgrade():
    op.add_column('matches', sa.Column('analysis_revision', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('matches', 'analysis_revision')
