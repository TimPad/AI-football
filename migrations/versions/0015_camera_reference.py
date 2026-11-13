"""Reference frame of a camera profile version: the processor checks the camera position against it."""

import sqlalchemy as sa
from alembic import op

revision = '0015_camera_reference'
down_revision = '0014_analysis_events'


def upgrade():
    op.add_column('camera_profiles', sa.Column('reference_sha256', sa.String(64), nullable=True))


def downgrade():
    op.drop_column('camera_profiles', 'reference_sha256')
