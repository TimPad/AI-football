"""Match broadcasts and public calendar lookup."""
from alembic import op
import sqlalchemy as sa

revision = '0005_broadcasts'
down_revision = '0004_protocol'


def upgrade():
    op.add_column('matches', sa.Column('broadcast_url', sa.String(2048)))
    op.add_column('matches', sa.Column('broadcast_embed_url', sa.String(2048)))
    op.create_index('ix_matches_tournament_schedule', 'matches', ['tournament_id', 'scheduled_at'])


def downgrade():
    op.drop_index('ix_matches_tournament_schedule', table_name='matches')
    op.drop_column('matches', 'broadcast_embed_url')
    op.drop_column('matches', 'broadcast_url')
