from alembic import op
revision='0025_analysis_queue_indexes'
down_revision='0024_team_confirmation_versions'
def upgrade():
    op.create_index('ix_analysis_job_match_created','analysis_jobs',['match_id','created_at','id'])
    op.create_index('ix_analysis_run_job_created','analysis_runs',['job_id','created_at','id'])
def downgrade():
    op.drop_index('ix_analysis_run_job_created',table_name='analysis_runs')
    op.drop_index('ix_analysis_job_match_created',table_name='analysis_jobs')
