"""Team profiles, permanent rosters and stable player profiles."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0006_team_profiles'
down_revision = '0005_broadcasts'


def upgrade():
    op.create_table('catalog_images', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False), sa.Column('size', sa.Integer(), nullable=False))
    for name in ['teams', 'players']:
        op.add_column(name, sa.Column('revision', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('teams', sa.Column('description', sa.String(4000), nullable=False, server_default=''))
    op.add_column('teams', sa.Column('logo_id', sa.Uuid(), sa.ForeignKey('catalog_images.id', name='fk_team_logo')))
    op.add_column('players', sa.Column('photo_id', sa.Uuid(), sa.ForeignKey('catalog_images.id', name='fk_player_photo')))
    op.add_column('players', sa.Column('birth_date', sa.Date()))
    op.add_column('players', sa.Column('position', sa.String(30)))
    op.add_column('players', sa.Column('height_cm', sa.Integer()))
    op.add_column('players', sa.Column('weight_kg', sa.Float()))
    op.create_table('team_members', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('team_id', sa.Uuid(), sa.ForeignKey('teams.id', name='fk_member_team'), nullable=False),
        sa.Column('player_id', sa.Uuid(), sa.ForeignKey('players.id', name='fk_member_player'), nullable=False),
        sa.Column('shirt_number', sa.String(10)), sa.Column('active', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('team_id', 'player_id', name='uq_team_member'))
    op.create_index('uq_team_active_number', 'team_members', ['team_id', 'shirt_number'], unique=True,
                    postgresql_where=sa.text('active'))
    op.create_table('team_profile_commands', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('team_id', sa.Uuid(), sa.ForeignKey('teams.id', name='fk_profile_command_team'), nullable=False),
        sa.Column('request_id', sa.Uuid(), nullable=False, unique=True),
        sa.Column('request_hash', sa.String(64), nullable=False), sa.Column('response', JSONB(), nullable=False))


def downgrade():
    op.drop_table('team_profile_commands')
    op.drop_table('team_members')
    for col in ['weight_kg', 'height_cm', 'position', 'birth_date', 'photo_id', 'revision']:
        op.drop_column('players', col)
    for col in ['logo_id', 'description', 'revision']:
        op.drop_column('teams', col)
    op.drop_table('catalog_images')
