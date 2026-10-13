from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0002_tournaments'
down_revision='0001_auth'


def upgrade():
    op.create_table('tournaments',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('name',sa.String(200),nullable=False),sa.Column('season',sa.String(100),nullable=False),
        sa.Column('starts_on',sa.Date(),nullable=False),sa.Column('ends_on',sa.Date(),nullable=False),
        sa.Column('timezone',sa.String(100),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('archived',sa.Boolean(),nullable=False))
    op.create_table('regulations',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('tournament_id',sa.Uuid(),sa.ForeignKey('tournaments.id',name='fk_regulation_tournament'),nullable=False),
        sa.Column('variant_name',sa.String(100),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('rules',JSONB(),nullable=False),sa.UniqueConstraint('tournament_id','variant_name','version',name='uq_regulation_version'))


def downgrade():
    op.drop_table('regulations'); op.drop_table('tournaments')
