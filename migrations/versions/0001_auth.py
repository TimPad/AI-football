from alembic import op
import sqlalchemy as sa

revision = '0001_auth'
down_revision = None


def upgrade():
    op.create_table('admins', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('login', sa.String(100), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False), sa.UniqueConstraint('login', name='uq_admin_login'))
    op.create_table('sessions', sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('admin_id', sa.Uuid(), sa.ForeignKey('admins.id', name='fk_session_admin'), nullable=False),
        sa.Column('csrf_token', sa.String(100), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('login_attempts', sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('login', sa.String(100), nullable=False), sa.Column('ip', sa.String(200), nullable=False),
        sa.Column('failed_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_login_attempts_login_ip_time', 'login_attempts', ['login', 'ip', 'failed_at'])


def downgrade():
    op.drop_table('login_attempts')
    op.drop_table('sessions')
    op.drop_table('admins')
