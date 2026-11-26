"""Players who did not take part in the match, per labelling version (analysis run).

The cabinet hides them from the identity queue and the server refuses to give them fragments. The list travels with
the labelling to newer versions; the manual protocol lineup is not touched.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = '0030_absent_players'
down_revision = '0029_camera_motion'


def upgrade():
    op.add_column(
        'analysis_runs',
        sa.Column('absent_players', JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade():
    op.drop_column('analysis_runs', 'absent_players')
