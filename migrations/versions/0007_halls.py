"""Halls, immutable camera geometry and match venue snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision='0007_halls'
down_revision='0006_team_profiles'


def entity_columns():
    return [sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False)]


def upgrade():
    op.create_table('halls',*entity_columns(),sa.Column('name',sa.String(200),nullable=False),
        sa.Column('address',sa.String(1000),nullable=False),sa.Column('pitch_length_m',sa.Float(),nullable=False),
        sa.Column('pitch_width_m',sa.Float(),nullable=False),sa.Column('ceiling_height_m',sa.Float()),
        sa.Column('latitude',sa.Float()),sa.Column('longitude',sa.Float()),
        sa.Column('surface',sa.String(200),nullable=False),sa.Column('description',sa.String(4000),nullable=False),
        sa.Column('archived',sa.Boolean(),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),
        sa.CheckConstraint('pitch_length_m > 0 AND pitch_length_m <= 300 AND pitch_width_m > 0 AND pitch_width_m <= 300',name='ck_hall_pitch'),
        sa.CheckConstraint('(latitude IS NULL AND longitude IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)',name='ck_hall_location'))
    op.create_table('hall_commands',*entity_columns(),
        sa.Column('hall_id',sa.Uuid(),sa.ForeignKey('halls.id',name='fk_hall_command'),nullable=False),
        sa.Column('request_id',sa.Uuid(),nullable=False,unique=True),sa.Column('request_hash',sa.String(64),nullable=False),
        sa.Column('response',JSONB(),nullable=False))
    op.create_table('camera_profiles',*entity_columns(),
        sa.Column('hall_id',sa.Uuid(),sa.ForeignKey('halls.id',name='fk_camera_hall'),nullable=False),
        sa.Column('name',sa.String(200),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('request_id',sa.Uuid(),nullable=False,unique=True),sa.Column('request_hash',sa.String(64),nullable=False),
        sa.Column('hall_revision',sa.Integer(),nullable=False),sa.Column('pitch_length_m',sa.Float(),nullable=False),
        sa.Column('pitch_width_m',sa.Float(),nullable=False),sa.Column('frame_width',sa.Integer(),nullable=False),
        sa.Column('frame_height',sa.Integer(),nullable=False),sa.Column('points',JSONB(),nullable=False),
        sa.Column('pitch_polygon_px',JSONB(),nullable=False),sa.Column('homography',JSONB(),nullable=False),
        sa.Column('calibration',JSONB()),sa.Column('reprojection_error_m',sa.Float(),nullable=False),
        sa.Column('leave_one_out_error_m',sa.Float()),sa.UniqueConstraint('hall_id','name','version',name='uq_camera_version'))
    op.add_column('matches',sa.Column('hall_id',sa.Uuid(),sa.ForeignKey('halls.id',name='fk_match_hall')))
    op.add_column('matches',sa.Column('hall_snapshot',JSONB()))
    op.add_column('matches',sa.Column('camera_profile_id',sa.Uuid(),sa.ForeignKey('camera_profiles.id',name='fk_match_camera')))
    op.create_index('ix_matches_hall_schedule','matches',['hall_id','scheduled_at'])


def downgrade():
    op.drop_index('ix_matches_hall_schedule',table_name='matches')
    for column in ['camera_profile_id','hall_snapshot','hall_id']: op.drop_column('matches',column)
    for table in ['camera_profiles','hall_commands','halls']: op.drop_table(table)
