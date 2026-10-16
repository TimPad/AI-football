from sqlalchemy import Column,String,Boolean,Integer,Float,Uuid,ForeignKey,UniqueConstraint,CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base,Entity


class Hall(Entity,Base):
    __tablename__='halls'
    name=Column(String(200),nullable=False)
    address=Column(String(1000),nullable=False)
    pitch_length_m=Column(Float,nullable=False)
    pitch_width_m=Column(Float,nullable=False)
    ceiling_height_m=Column(Float)
    latitude=Column(Float)
    longitude=Column(Float)
    surface=Column(String(200),nullable=False,default='')
    description=Column(String(4000),nullable=False,default='')
    archived=Column(Boolean,nullable=False,default=False)
    revision=Column(Integer,nullable=False,default=0)
    __table_args__=(CheckConstraint('pitch_length_m > 0 AND pitch_length_m <= 300 AND pitch_width_m > 0 AND pitch_width_m <= 300',name='ck_hall_pitch'),
        CheckConstraint('(latitude IS NULL AND longitude IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)',name='ck_hall_location'),)


class HallCommand(Entity,Base):
    __tablename__='hall_commands'
    hall_id=Column(Uuid,ForeignKey('halls.id',name='fk_hall_command'),nullable=False)
    request_id=Column(Uuid,nullable=False,unique=True)
    request_hash=Column(String(64),nullable=False)
    response=Column(JSONB,nullable=False)


class CameraProfile(Entity,Base):
    __tablename__='camera_profiles'
    hall_id=Column(Uuid,ForeignKey('halls.id',name='fk_camera_hall'),nullable=False)
    name=Column(String(200),nullable=False)
    version=Column(Integer,nullable=False)
    request_id=Column(Uuid,nullable=False,unique=True)
    request_hash=Column(String(64),nullable=False)
    hall_revision=Column(Integer,nullable=False)
    pitch_length_m=Column(Float,nullable=False)
    pitch_width_m=Column(Float,nullable=False)
    frame_width=Column(Integer,nullable=False)
    frame_height=Column(Integer,nullable=False)
    points=Column(JSONB,nullable=False)
    pitch_polygon_px=Column(JSONB,nullable=False)
    homography=Column(JSONB,nullable=False)
    calibration=Column(JSONB)
    reprojection_error_m=Column(Float,nullable=False)
    leave_one_out_error_m=Column(Float)
    reference_sha256=Column(String(64))  # эталонный кадр этой версии (camera-frames/<id>.jpg), задаётся один раз
    __table_args__=(UniqueConstraint('hall_id','name','version',name='uq_camera_version'),)
