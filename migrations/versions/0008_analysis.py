"""Analytics capability, external jobs, reviewed versions and player metrics."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0008_analysis'
down_revision = '0007_halls'


def entity():
    return [sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False)]


def fk(name, target, nullable=False):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(target), nullable=nullable)


def upgrade():
    op.add_column('admins', sa.Column('can_manage_analytics', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table('analysis_jobs', *entity(), fk('match_id', 'matches.id'), fk('created_by', 'admins.id'),
                    sa.Column('context_hash', sa.String(64), nullable=False),
                    sa.Column('context', JSONB, nullable=False), sa.Column('cv_files', JSONB, nullable=False))
    op.create_table('analysis_runs', *entity(), fk('job_id', 'analysis_jobs.id'), fk('match_id', 'matches.id'),
                    fk('created_by', 'admins.id'), fk('source_run_id', 'analysis_runs.id', True),
                    sa.Column('content_hash', sa.String(64), nullable=False),
                    sa.Column('storage_key', sa.String(100), nullable=False),
                    *[sa.Column(key, JSONB, nullable=False) for key in ['manifest', 'report', 'tracks', 'checks', 'side_map']],
                    sa.Column('status', sa.String(20), nullable=False), sa.Column('revision', sa.Integer(), nullable=False),
                    fk('confirmed_by', 'admins.id', True))
    op.create_index('uq_analysis_import_content', 'analysis_runs', ['job_id', 'content_hash'], unique=True,
                    postgresql_where=sa.text('source_run_id IS NULL'))
    op.create_table('analysis_assignments',
                    sa.Column('run_id', sa.Uuid(), sa.ForeignKey('analysis_runs.id'), primary_key=True),
                    sa.Column('track_id', sa.Integer(), primary_key=True), fk('player_id', 'players.id', True),
                    sa.Column('excluded_reason', sa.String(500)))
    op.create_table('player_match_metrics',
                    sa.Column('run_id', sa.Uuid(), sa.ForeignKey('analysis_runs.id'), primary_key=True),
                    sa.Column('player_id', sa.Uuid(), sa.ForeignKey('players.id'), primary_key=True),
                    fk('match_id', 'matches.id'), sa.Column('display_name', sa.String(200), nullable=False),
                    sa.Column('shirt_number', sa.String(10)), sa.Column('side', sa.String(10), nullable=False),
                    sa.Column('track_ids', JSONB, nullable=False), sa.Column('metrics', JSONB, nullable=False))
    op.create_index('ix_player_match_metrics_match_id', 'player_match_metrics', ['match_id'])
    op.create_table('analysis_commands', *entity(), fk('match_id', 'matches.id'), fk('actor_id', 'admins.id'),
                    sa.Column('request_id', sa.Uuid(), nullable=False),
                    sa.Column('request_hash', sa.String(64), nullable=False), sa.Column('response', JSONB, nullable=False),
                    sa.UniqueConstraint('match_id', 'request_id', name='uq_analysis_command_request'))
    for name in ['active_analysis_run_id', 'published_analysis_run_id']:
        op.add_column('matches', sa.Column(name, sa.Uuid()))
        op.create_foreign_key('fk_match_' + name, 'matches', 'analysis_runs', [name], ['id'])


def downgrade():
    for name in ['active_analysis_run_id', 'published_analysis_run_id']:
        op.drop_constraint('fk_match_' + name, 'matches', type_='foreignkey')
        op.drop_column('matches', name)
    for name in ['analysis_commands', 'player_match_metrics', 'analysis_assignments', 'analysis_runs', 'analysis_jobs']:
        op.drop_table(name)
    op.drop_column('admins', 'can_manage_analytics')
