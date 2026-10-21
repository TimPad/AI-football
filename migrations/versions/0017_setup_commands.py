from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0017_setup_commands'
down_revision = '0016_tournament_visibility'


def upgrade():
    op.create_table('setup_commands',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actor_id', sa.Uuid(), sa.ForeignKey('admins.id'), nullable=False),
        sa.Column('request_id', sa.Uuid(), nullable=False, unique=True),
        sa.Column('kind', sa.String(50), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('response', JSONB(), nullable=False))


def downgrade():
    op.drop_table('setup_commands')
