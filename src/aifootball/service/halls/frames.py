"""Эталонный кадр версии профиля камеры: приватный JPEG без метаданных в хранилище вложений.

По нему обработчик сверяет, не сдвинута ли камера к моменту записи (geometry.camera_drift).
Кадр задаётся один раз: перенастроенной камере нужна новая версия профиля.
"""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID
import os
import warnings
from PIL import Image, UnidentifiedImageError
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from aifootball.service.auth.security import require_admin, require_csrf
from aifootball.service.common import get_entity
from aifootball.service.db import get_session
from aifootball.service.errors import DomainError
from aifootball.service.halls.models import CameraProfile, Hall
from aifootball.service.halls.operations import camera_view
from aifootball.service.views import CameraProfileView

router = APIRouter()
MAX_BYTES = 16 * 1024 * 1024
MAX_PIXELS = 40_000_000


def reference_path(root, profile_id) -> Path:
    return Path(root) / 'camera-frames' / f'{profile_id}.jpg'


def normalized_jpeg(raw: bytes, content_type: str | None) -> tuple[bytes, int, int]:
    """JPEG/PNG/WebP -> JPEG без EXIF и прочих метаданных; кодирование детерминировано (повтор даёт тот же хэш)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                if image.format not in {'PNG', 'JPEG', 'WEBP'} or content_type != Image.MIME.get(image.format):
                    raise DomainError('file_type', 'Загрузите кадр в формате JPEG, PNG или WebP')
                if image.width * image.height > MAX_PIXELS:
                    raise DomainError('image_size', 'Кадр слишком большой: максимум 40 миллионов пикселей')
                image.load()
                clean = Image.new('RGB', image.size); clean.paste(image.convert('RGB'))
                output = BytesIO(); clean.save(output, format='JPEG', quality=95)
                return output.getvalue(), clean.width, clean.height
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise DomainError('file_type', 'Не удалось прочитать кадр. Загрузите корректный JPEG, PNG или WebP')


def _profile(db, hid, pid, lock=False):
    profile = get_entity(db, CameraProfile, pid, lock=lock)
    if profile.hall_id != hid:
        raise DomainError('not_found', 'Профиль камеры не найден', status=404)
    return profile


@router.put('/halls/{hid}/camera-profiles/{pid}/reference-frame', response_model=CameraProfileView)
def upload_reference(hid: UUID, pid: UUID, request: Request, file: UploadFile = File(),
                     db: Session = Depends(get_session), actor=Depends(require_csrf)):
    raw = file.file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise DomainError('file_size', 'Кадр должен быть не больше 16 МБ')
    encoded, width, height = normalized_jpeg(raw, file.content_type)
    digest = sha256(encoded).hexdigest()
    with db.begin():
        profile = _profile(db, hid, pid, lock=True)
        if (width, height) != (profile.frame_width, profile.frame_height):
            raise DomainError('image_size', f'Кадр {width} × {height} px, а профиль камеры — {profile.frame_width} × {profile.frame_height} px. '
                                            'Загрузите кадр той же камеры в том же разрешении')
        hall = get_entity(db, Hall, hid)
        if profile.reference_sha256:
            if profile.reference_sha256 != digest:
                raise DomainError('reference_set', 'Эталонный кадр этой версии уже задан. Если камеру перенастроили, создайте новую версию профиля',
                                  status=409)
            return camera_view(profile, hall)
        target = reference_path(request.app.state.settings.attachment_root, profile.id)
        target.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
            path = Path(temporary.name)
            try:
                temporary.write(encoded); temporary.flush()
                os.replace(path, target); target.chmod(0o600)
            finally:
                path.unlink(missing_ok=True)
        profile.reference_sha256 = digest
        db.flush()
        return camera_view(profile, hall)


@router.get('/halls/{hid}/camera-profiles/{pid}/reference-frame', dependencies=[Depends(require_admin)])
def reference_frame(hid: UUID, pid: UUID, request: Request, db: Session = Depends(get_session)):
    profile = _profile(db, hid, pid)
    path = reference_path(request.app.state.settings.attachment_root, profile.id)
    if not profile.reference_sha256 or not path.is_file():
        raise DomainError('not_found', 'Эталонный кадр не загружен', status=404)
    return FileResponse(path, media_type='image/jpeg', headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, max-age=3600'})
