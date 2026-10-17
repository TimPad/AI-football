from alembic import op
import sqlalchemy as sa
revision='0019_hall_addresses'
down_revision='0018_roster_imports'
def upgrade():
    op.add_column('halls',sa.Column('address_source',sa.String(10),nullable=False,server_default='manual'))
    op.create_check_constraint('ck_hall_address_source','halls',"address_source IN ('manual','yandex')")
    op.create_table('hall_address_limits',sa.Column('actor_id',sa.Uuid(),sa.ForeignKey('admins.id',name='fk_hall_address_actor'),primary_key=True),sa.Column('window',sa.BigInteger(),nullable=False),sa.Column('count',sa.Integer(),nullable=False))
def downgrade():
    op.drop_table('hall_address_limits')
    op.drop_constraint('ck_hall_address_source','halls')
    op.drop_column('halls','address_source')
