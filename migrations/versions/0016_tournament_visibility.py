"""Keep existing public URLs while new tournaments start privately."""
from alembic import op
import sqlalchemy as sa

revision = '0016_tournament_visibility'
down_revision = '0015_camera_reference'


def upgrade():
    op.add_column('tournaments', sa.Column('visibility', sa.String(10), nullable=False, server_default='public'))
    op.alter_column('tournaments', 'visibility', server_default='draft')
    op.create_check_constraint('ck_tournament_visibility', 'tournaments', "visibility IN ('draft','public')")


def downgrade():
    op.drop_constraint('ck_tournament_visibility', 'tournaments', type_='check')
    op.drop_column('tournaments', 'visibility')
