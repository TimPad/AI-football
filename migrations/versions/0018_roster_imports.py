from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0018_roster_imports'
down_revision = '0017_setup_commands'


def upgrade():
    op.create_table('roster_imports',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actor_kind', sa.String(10), nullable=False),
        sa.Column('actor_id', sa.Uuid(), nullable=False),
        sa.Column('scope', sa.String(20), nullable=False),
        sa.Column('target_id', sa.Uuid(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', JSONB(), nullable=False),
        sa.Column('configuration', JSONB(), nullable=False),
        sa.Column('rows', JSONB(), nullable=False),
        sa.Column('expected', JSONB(), nullable=False),
        sa.Column('summary', JSONB(), nullable=False),
        sa.Column('commit_request_id', sa.Uuid(), unique=True),
        sa.Column('commit_revision', sa.Integer()),
        sa.Column('result', JSONB()),
        sa.CheckConstraint("scope IN ('team','tournament') AND actor_kind IN ('admin','captain')", name='ck_roster_import_scope'))
    op.create_index('ix_roster_import_actor', 'roster_imports', ['actor_kind', 'actor_id'])


def downgrade():
    op.drop_table('roster_imports')
