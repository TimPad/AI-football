"""Stage participants per draw version, technical pair outcomes and team withdrawals."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0028_stage_adjustments'
down_revision = '0027_tournament_stages'


def upgrade():
    op.add_column('stage_draws', sa.Column('participants', JSONB()))
    op.add_column('fixtures', sa.Column('outcome', JSONB()))
    op.create_table('stage_withdrawals',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('stage_id', sa.Uuid(), sa.ForeignKey('stages.id', name='fk_withdrawal_stage'), nullable=False),
        sa.Column('entry_id', sa.Uuid(), sa.ForeignKey('entries.id', name='fk_withdrawal_entry'), nullable=False),
        sa.Column('rule', sa.String(20), nullable=False),
        sa.Column('played', sa.Integer(), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Uuid(), sa.ForeignKey('admins.id', name='fk_withdrawal_admin'), nullable=False),
        sa.UniqueConstraint('stage_id', 'entry_id', name='uq_stage_withdrawal'),
        sa.CheckConstraint("rule in ('annul','walkover','elimination','swiss')", name='ck_withdrawal_rule'))


def downgrade():
    op.drop_table('stage_withdrawals')
    op.drop_column('fixtures', 'outcome')
    op.drop_column('stage_draws', 'participants')
