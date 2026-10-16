from io import BytesIO
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
import json
from uuid import UUID
from fastapi import APIRouter,Depends,Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from aifootball.service.db import get_session
from aifootball.service.common import get_entity,as_dict,list_entities
from aifootball.service.auth.security import require_admin,require_csrf
from aifootball.service.errors import DomainError
from aifootball.service.halls.models import Hall,CameraProfile
from aifootball.service.halls.schemas import HallCreate,HallUpdate,CameraCreate
from aifootball.service.halls.operations import save_hall,make_camera,camera_view,same_dimensions
from aifootball.service.views import Page,HallView,CameraProfileView
from aifootball.service.matches.models import Match

router=APIRouter()


@router.get('/halls',response_model=Page[HallView],dependencies=[Depends(require_admin)])
def halls(db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    return list_entities(db,Hall,limit=limit,offset=offset)


@router.get('/halls/{hid}',response_model=HallView,dependencies=[Depends(require_admin)])
def hall(hid:UUID,db:Session=Depends(get_session)): return as_dict(get_entity(db,Hall,hid))


@router.post('/halls',response_model=HallView,status_code=201,dependencies=[Depends(require_csrf)])
def create(data:HallCreate,db:Session=Depends(get_session)):
    with db.begin(): return save_hall(db,data)


@router.put('/halls/{hid}',response_model=HallView,dependencies=[Depends(require_csrf)])
def update(hid:UUID,data:HallUpdate,db:Session=Depends(get_session)):
    with db.begin(): return save_hall(db,data,hid)


@router.get('/halls/{hid}/camera-profiles',response_model=Page[CameraProfileView],dependencies=[Depends(require_admin)])
def profiles(hid:UUID,db:Session=Depends(get_session),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    hall=get_entity(db,Hall,hid)
    result=list_entities(db,CameraProfile,where=[CameraProfile.hall_id==hid],limit=limit,offset=offset)
    result['items']=[{**p,'matches_current_dimensions':p['pitch_length_m']==hall.pitch_length_m and p['pitch_width_m']==hall.pitch_width_m} for p in result['items']]
    return result


@router.post('/halls/{hid}/camera-profiles',response_model=CameraProfileView,status_code=201,dependencies=[Depends(require_csrf)])
def create_profile(hid:UUID,data:CameraCreate,db:Session=Depends(get_session)):
    with db.begin(): return make_camera(db,hid,data)


@router.get('/matches/{mid}/cv-config',dependencies=[Depends(require_admin)])
def export_cv(mid:UUID,db:Session=Depends(get_session)):
    match=get_entity(db,Match,mid)
    if not match.hall_snapshot or not match.camera_profile_id:
        raise DomainError('camera_required','Выберите зал и калиброванный профиль камеры в информации о матче')
    profile=get_entity(db,CameraProfile,match.camera_profile_id)
    if profile.hall_id!=match.hall_id or not same_dimensions(profile,match.hall_snapshot):
        raise DomainError('camera_geometry','Профиль камеры не соответствует размерам матча')
    import yaml
    # target_fps — предел: обработчик берёт частоту видео (25 → 25, 30 → 30), чаще 30 — каждый k-й кадр (60 → 30).
    # Передачи по мячу требуют не меньше 15 кадров/с (processor.job.EVENTS_MIN_FPS).
    settings={'venue_id':str(match.hall_id),'pitch':{'length_m':profile.pitch_length_m,'width_m':profile.pitch_width_m},
        'processing':{'model':'yolo11m.pt','imgsz':1280,'target_fps':30,'conf_person':0.3,'conf_ball':0.1,
            'frame_width':profile.frame_width,'frame_height':profile.frame_height,'camera_profile_id':str(profile.id)}}
    files={'venue.yaml':yaml.safe_dump(settings,allow_unicode=True),
        'homography.json':json.dumps({'H':profile.homography,'points':profile.points,
            'reprojection_error_m':profile.reprojection_error_m,'leave_one_out_error_m':profile.leave_one_out_error_m}),
        'pitch_polygon.json':json.dumps({'points_px':profile.pitch_polygon_px}),
        'source.json':json.dumps({'match_id':str(match.id),'hall':match.hall_snapshot,
            'camera_profile_id':str(profile.id),'camera_profile_version':profile.version},ensure_ascii=False)}
    if profile.calibration: files['calib.json']=json.dumps(profile.calibration)
    buffer=BytesIO()
    with ZipFile(buffer,'w',compression=ZIP_DEFLATED) as archive:
        for name,value in files.items():
            info=ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=ZIP_DEFLATED
            archive.writestr(info,value.encode())
    return Response(buffer.getvalue(),media_type='application/zip',headers={
        'Content-Disposition':f'attachment; filename="cv-{mid}.zip"','Cache-Control':'private, no-store'})
