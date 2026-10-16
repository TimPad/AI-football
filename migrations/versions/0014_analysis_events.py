"""Ball events of an imported CV run (result contract 3): passes for automatic team statistics."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0014_analysis_events'
down_revision='0013_tournament_ratings'


def upgrade():
    op.add_column('analysis_runs',sa.Column('events',JSONB(),nullable=True))


def downgrade():
    op.drop_column('analysis_runs','events')
