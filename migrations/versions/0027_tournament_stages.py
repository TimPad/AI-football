"""Tournament stages: confirmed draw versions and stage fixtures."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0027_tournament_stages'
down_revision = '0026_registration_credentials'


def upgrade():
    op.add_column('tournaments', sa.Column('standings_public', sa.Boolean(), nullable=False, server_default='true'))
    op.create_table('stages',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tournament_id', sa.Uuid(), sa.ForeignKey('tournaments.id', name='fk_stage_tournament'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('regulation_id', sa.Uuid(), sa.ForeignKey('regulations.id', name='fk_stage_regulation'), nullable=False),
        sa.Column('config', JSONB(), nullable=False),
        sa.Column('lots', JSONB(), nullable=False, server_default='{}'),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.UniqueConstraint('tournament_id', 'position', name='uq_stage_position'),
        sa.CheckConstraint("kind in ('round_robin','groups','single_elim','double_elim','swiss')", name='ck_stage_kind'))
    op.create_table('stage_draws',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('stage_id', sa.Uuid(), sa.ForeignKey('stages.id', name='fk_draw_stage'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('method', sa.String(20), nullable=False),
        sa.Column('seed', sa.Integer(), nullable=False),
        sa.Column('seeding', JSONB(), nullable=False),
        sa.Column('placement', JSONB(), nullable=False),
        sa.Column('confirmed_by', sa.Uuid(), sa.ForeignKey('admins.id', name='fk_draw_admin'), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('stage_id', 'version', name='uq_stage_draw_version'))
    op.create_table('fixtures',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('stage_id', sa.Uuid(), sa.ForeignKey('stages.id', name='fk_fixture_stage'), nullable=False),
        sa.Column('draw_id', sa.Uuid(), sa.ForeignKey('stage_draws.id', name='fk_fixture_draw'), nullable=False),
        sa.Column('key', sa.String(20), nullable=False),
        sa.Column('leg', sa.Integer(), nullable=False),
        sa.Column('group_no', sa.Integer()),
        sa.Column('round_no', sa.Integer(), nullable=False),
        sa.Column('bracket', sa.String(20)),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('home_entry_id', sa.Uuid(), sa.ForeignKey('entries.id', name='fk_fixture_home')),
        sa.Column('away_entry_id', sa.Uuid(), sa.ForeignKey('entries.id', name='fk_fixture_away')),
        sa.Column('home_source', JSONB()),
        sa.Column('away_source', JSONB()),
        sa.Column('bye', sa.Boolean(), nullable=False),
        sa.Column('match_id', sa.Uuid(), sa.ForeignKey('matches.id', name='fk_fixture_match'), unique=True),
        sa.UniqueConstraint('draw_id', 'key', 'leg', name='uq_fixture_key'),
        sa.CheckConstraint('home_entry_id is null or away_entry_id is null or home_entry_id != away_entry_id', name='ck_fixture_teams'))
    op.create_index('ix_stages_tournament_id', 'stages', ['tournament_id'])
    op.create_index('ix_fixtures_stage_id', 'fixtures', ['stage_id'])


def downgrade():
    op.drop_index('ix_fixtures_stage_id', table_name='fixtures')
    op.drop_index('ix_stages_tournament_id', table_name='stages')
    op.drop_table('fixtures')
    op.drop_table('stage_draws')
    op.drop_table('stages')
    op.drop_column('tournaments', 'standings_public')
