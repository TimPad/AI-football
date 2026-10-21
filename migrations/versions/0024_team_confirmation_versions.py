from alembic import op
import sqlalchemy as sa
revision='0024_team_confirmation_versions'
down_revision='0023_team_identity'

def upgrade():
    op.add_column('team_identity_confirmations',sa.Column('version',sa.Integer(),nullable=False,server_default='1'))
    op.execute('''UPDATE team_identity_confirmations c SET version=n.version FROM
        (SELECT id,row_number() OVER (PARTITION BY run_id,side ORDER BY created_at,id) AS version FROM team_identity_confirmations) n WHERE c.id=n.id''')
    op.alter_column('team_identity_confirmations','version',server_default=None)
    op.create_unique_constraint('uq_team_confirmation_version','team_identity_confirmations',['run_id','side','version'])

def downgrade():
    op.drop_constraint('uq_team_confirmation_version','team_identity_confirmations',type_='unique')
    op.drop_column('team_identity_confirmations','version')
