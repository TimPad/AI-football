"""Hall snapshots and camera geometry; no detector imports in the HTTP app."""
import json
from hashlib import sha256
from uuid import uuid5,NAMESPACE_URL
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select,func
from aifootball.service.common import get_entity,as_dict
from aifootball.service.errors import DomainError
from aifootball.service.halls.models import Hall,HallCommand,CameraProfile
from aifootball.service.halls.schemas import HallFields


def digest(data,identifier):
    return sha256(json.dumps({'id':str(identifier),'data':data.model_dump(mode='json',exclude={'address_selection_token'} if getattr(data,'address_selection_token',None) is None else set())},
        sort_keys=True,separators=(',',':')).encode()).hexdigest()


def lock_request(db,identifier):
    db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(identifier.bytes[:8],signed=True))))


def save_hall(db,data,hall_id=None,*,settings=None,actor=None):
    lock_request(db,data.request_id)
    hashed=digest(data,hall_id)
    prior=db.scalar(select(HallCommand).where(HallCommand.request_id==data.request_id))
    if prior:
        if prior.request_hash!=hashed: raise DomainError('idempotency_conflict','Ключ сохранения уже использован',status=409)
        return prior.response
    if hall_id:
        hall=get_entity(db,Hall,hall_id,lock=True)
        if hall.revision!=data.expected_revision:
            raise DomainError('revision_conflict','Зал изменён в другом окне. Обновите карточку.',status=409,current_revision=hall.revision)
        hall.archived=data.archived
    else:
        hall=Hall(id=uuid5(NAMESPACE_URL,'aifootball:hall:'+str(data.request_id)))
        db.add(hall)
    old=(hall.address,hall.latitude,hall.longitude,hall.address_source) if hall_id else None
    if data.address_selection_token:
        from aifootball.service.halls.address_provider import validate_selection
        if settings is None or actor is None:raise DomainError('address_selection','Выберите адрес заново.',status=422)
        validate_selection(settings,actor,data)
    for field in HallFields.model_fields: setattr(hall,field,getattr(data,field))
    if data.address_selection_token:hall.address_source='yandex'
    elif old and old[0]==data.address and (not {'latitude','longitude'}&data.model_fields_set or (data.latitude,data.longitude)==old[1:3]):
        hall.latitude,hall.longitude,hall.address_source=old[1:]
    else:
        hall.address_source='manual'
        if old and old[0]!=data.address:hall.latitude=None;hall.longitude=None
    hall.revision=(hall.revision or 0)+1
    db.flush()
    response=jsonable_encoder(as_dict(hall))
    db.add(HallCommand(hall_id=hall.id,request_id=data.request_id,request_hash=hashed,response=response))
    return response


def same_dimensions(profile,geometry):
    return profile.pitch_length_m==geometry['pitch_length_m'] and profile.pitch_width_m==geometry['pitch_width_m']


def camera_view(profile,hall):
    return {**as_dict(profile),'matches_current_dimensions':same_dimensions(profile,as_dict(hall))}


def make_camera(db,hall_id,data):
    lock_request(db,data.request_id)
    hashed=digest(data,hall_id)
    prior=db.scalar(select(CameraProfile).where(CameraProfile.request_id==data.request_id))
    if prior:
        if prior.request_hash!=hashed: raise DomainError('idempotency_conflict','Ключ профиля уже использован',status=409)
        return camera_view(prior,get_entity(db,Hall,hall_id))
    hall=get_entity(db,Hall,hall_id,lock=True)
    if hall.archived: raise DomainError('archived','Зал находится в архиве')
    if hall.revision!=data.expected_hall_revision:
        raise DomainError('revision_conflict','Размеры зала могли измениться. Обновите карточку.',status=409,current_revision=hall.revision)
    H,error,loo=calculate_geometry(data,hall)
    version=(db.scalar(select(func.max(CameraProfile.version)).where(CameraProfile.hall_id==hall_id,CameraProfile.name==data.name)) or 0)+1
    values=data.model_dump(mode='json',exclude={'expected_hall_revision'})
    values['request_id']=data.request_id
    profile=CameraProfile(id=uuid5(NAMESPACE_URL,'aifootball:camera:'+str(data.request_id)),hall_id=hall_id,
        version=version,hall_revision=hall.revision,pitch_length_m=hall.pitch_length_m,pitch_width_m=hall.pitch_width_m,
        homography=H,request_hash=hashed,reprojection_error_m=error,leave_one_out_error_m=loo,**values)
    db.add(profile);db.flush()
    return camera_view(profile,hall)


def calculate_geometry(data,hall):
    import numpy as np
    import cv2
    from aifootball.geometry.homography import fit_homography,leave_one_out_error
    from aifootball.geometry.polygons import is_simple_polygon
    from aifootball.geometry.undistort import undistort_points
    from aifootball.venue import Calibration
    px=np.array([p.px for p in data.points]); meters=np.array([p.m for p in data.points])
    polygon=np.asarray(data.pitch_polygon_px)
    def fail(message): raise DomainError('camera_geometry',message)
    def in_frame(points):
        return bool(np.all((points[:,0]>=0)&(points[:,0]<data.frame_width)&(points[:,1]>=0)&(points[:,1]<data.frame_height)))
    if not in_frame(px) or not in_frame(polygon): fail('Пиксельные точки должны находиться внутри кадра указанного размера')
    if not np.all((meters[:,0]>=0)&(meters[:,0]<=hall.pitch_length_m)&(meters[:,1]>=0)&(meters[:,1]<=hall.pitch_width_m)):
        fail('Координаты в метрах должны находиться внутри игровой площадки зала')
    if len(np.unique(px,axis=0))!=len(px) or len(np.unique(meters,axis=0))!=len(meters): fail('Опорные точки не должны повторяться')
    if np.linalg.matrix_rank(px-px.mean(axis=0))<2 or np.linalg.matrix_rank(meters-meters.mean(axis=0))<2:
        fail('Опорные точки не должны лежать на одной прямой')
    if len(np.unique(polygon,axis=0))!=len(polygon) or not is_simple_polygon(polygon) or abs(cv2.contourArea(polygon.astype(np.float32)))<1:
        fail('Контур поля должен иметь площадь и не пересекать сам себя')
    calibration=Calibration(np.array(data.calibration.K),np.array(data.calibration.dist)) if data.calibration else None
    ideal=undistort_points(px,calibration)
    try:
        H,error=fit_homography(ideal,meters)
        if not np.isfinite(H).all() or abs(np.linalg.det(H))<1e-12: fail('Опорные точки не задают устойчивое преобразование')
        # A homography can fit four swapped corners exactly while its horizon
        # crosses the pitch. Such a map makes interior distances meaningless.
        ideal_polygon=undistort_points(polygon,calibration)
        denominator=np.column_stack((ideal_polygon,np.ones(len(polygon))))@H[2]
        if not np.isfinite(denominator).all() or not (np.all(denominator>1e-9) or np.all(denominator<-1e-9)):
            fail('Преобразование разрывается внутри поля. Проверьте порядок и соответствие точек.')
        loo=leave_one_out_error(ideal,meters) if len(px)>4 else None
        if not np.isfinite(error) or (loo is not None and not np.isfinite(loo)): fail('Не удалось проверить преобразование')
    except (ValueError,np.linalg.LinAlgError,cv2.error) as exc:
        raise DomainError('camera_geometry','Не удалось рассчитать калибровку. Проверьте соответствие точек.') from exc
    return H.tolist(),float(error),float(loo) if loo is not None else None


def assign_match_hall(db,match,hall_id,camera_id=None,*,camera_explicit=False):
    if hall_id is None: raise DomainError('hall_required','Выберите зал из справочника')
    hall=get_entity(db,Hall,hall_id,lock=True)
    changed=match.hall_id!=hall_id or not match.hall_snapshot
    if changed:
        if hall.archived: raise DomainError('archived','Выберите действующий зал')
        match.hall_id=hall.id
        match.hall_snapshot=jsonable_encoder(as_dict(hall))
        match.venue_label=hall.name
        match.camera_profile_id=None
    if camera_explicit:
        if camera_id:
            profile=get_entity(db,CameraProfile,camera_id)
            if profile.hall_id!=hall_id or not same_dimensions(profile,match.hall_snapshot):
                raise DomainError('foreign_camera','Профиль камеры должен относиться к выбранному залу и размерам матча')
        match.camera_profile_id=camera_id
