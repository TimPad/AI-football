"""Camera motion of a profile version: fixed or a broadcast camera with pan and zoom (ptz).

A ptz version has no hand-marked pitch outline (the processor derives it from the homography),
lists the broadcast graphics as frame fractions and may hold a replay badge template.
Existing versions stay fixed with their outline.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = '0029_camera_motion'
down_revision = '0028_stage_adjustments'


def upgrade():
    op.add_column(
        'camera_profiles', sa.Column('motion', sa.String(10), nullable=False, server_default=sa.text("'fixed'"))
    )
    op.add_column('camera_profiles', sa.Column('overlay', JSONB()))
    op.add_column('camera_profiles', sa.Column('replay_badge', JSONB()))
    op.alter_column('camera_profiles', 'pitch_polygon_px', existing_type=JSONB(), nullable=True)
    op.create_check_constraint(
        'ck_camera_motion',
        'camera_profiles',
        "(motion = 'fixed' AND pitch_polygon_px IS NOT NULL AND overlay IS NULL AND replay_badge IS NULL)"
        " OR (motion = 'ptz' AND pitch_polygon_px IS NULL AND overlay IS NOT NULL)",
    )


def downgrade():
    # Поворотный профиль без контура в прежней схеме не выразить, а удалить его — потерять матчи и задания.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM camera_profiles WHERE motion = 'ptz'")):
        raise RuntimeError('Есть профили поворотной камеры: откат схемы их потеряет')
    op.drop_constraint('ck_camera_motion', 'camera_profiles', type_='check')
    op.alter_column('camera_profiles', 'pitch_polygon_px', existing_type=JSONB(), nullable=False)
    op.drop_column('camera_profiles', 'replay_badge')
    op.drop_column('camera_profiles', 'overlay')
    op.drop_column('camera_profiles', 'motion')
