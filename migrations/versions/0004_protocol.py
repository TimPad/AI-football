from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0004_protocol'
down_revision='0003_matches'


def upgrade():
    op.create_table('protocol_versions',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('match_id',sa.Uuid(),sa.ForeignKey('matches.id',name='fk_version_match'),nullable=False),
        sa.Column('number',sa.Integer(),nullable=False),sa.Column('snapshot',JSONB(),nullable=False),
        sa.Column('confirmed_by',sa.Uuid(),sa.ForeignKey('admins.id',name='fk_version_admin'),nullable=False),
        sa.Column('confirmed_at',sa.DateTime(timezone=True),nullable=False),sa.Column('published_at',sa.DateTime(timezone=True)),
        sa.Column('public_id',sa.Uuid()),sa.UniqueConstraint('public_id',name='uq_version_public_id'),
        sa.UniqueConstraint('match_id','number',name='uq_protocol_version'))
    op.create_foreign_key('fk_match_published','matches','protocol_versions',['published_version_id'],['id'])
    op.create_table('attachments',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('match_id',sa.Uuid(),sa.ForeignKey('matches.id',name='fk_attachment_match'),nullable=False),
        sa.Column('original_name',sa.String(300),nullable=False),sa.Column('storage_key',sa.String(100),nullable=False),
        sa.Column('mime',sa.String(100),nullable=False),sa.Column('size',sa.Integer(),nullable=False),
        sa.Column('sha256',sa.String(64),nullable=False),sa.Column('removed_at',sa.DateTime(timezone=True)),
        sa.Column('created_by',sa.Uuid(),sa.ForeignKey('admins.id',name='fk_attachment_admin'),nullable=False))


def downgrade():
    op.drop_table('attachments'); op.drop_constraint('fk_match_published','matches',type_='foreignkey'); op.drop_table('protocol_versions')
