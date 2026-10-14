"""Private normalized profile images. No HTML/SVG or arbitrary file paths."""
from io import BytesIO
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID, uuid5, NAMESPACE_URL
import os
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import APIRouter, Depends, File, UploadFile, Request, Header
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from aifootball.service.auth.security import require_admin, require_csrf
from aifootball.service.db import get_session
from aifootball.service.common import get_entity, as_dict
from aifootball.service.errors import DomainError
from aifootball.service.catalog.models import CatalogImage
from aifootball.service.views import CatalogImageView

router = APIRouter(prefix='/catalog/images')
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000


@router.post('', response_model=CatalogImageView, status_code=201)
def upload(request: Request, file: UploadFile = File(), request_id: UUID = Header(alias='X-Request-ID'),
           db: Session = Depends(get_session), actor=Depends(require_csrf)):
    raw = file.file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES: raise DomainError('file_size', 'Фото или логотип должны быть не больше 5 МБ')
    digest = sha256(raw).hexdigest()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                if image.format not in {'PNG', 'JPEG', 'WEBP'} or file.content_type != Image.MIME.get(image.format):
                    raise DomainError('file_type', 'Загрузите изображение PNG, JPEG или WebP')
                if image.width * image.height > MAX_PIXELS: raise DomainError('image_size', 'Изображение слишком большое: максимум 16 миллионов пикселей')
                image.load()
                clean = ImageOps.exif_transpose(image).convert('RGBA' if image.mode in {'RGBA', 'P'} else 'RGB')
                clean.thumbnail((1200, 1200))
                # New image removes EXIF and all inherited metadata.
                normalized = Image.new(clean.mode, clean.size); normalized.paste(clean)
                output = BytesIO(); normalized.save(output, format='PNG'); encoded = output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise DomainError('file_type', 'Не удалось прочитать изображение. Загрузите корректный PNG, JPEG или WebP')
    identifier = uuid5(NAMESPACE_URL, 'aifootball:catalog-image:' + str(request_id))
    root = Path(request.app.state.settings.attachment_root) / 'catalog'
    with db.begin():
        db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(request_id.bytes[:8], signed=True))))
        old = db.get(CatalogImage, identifier)
        if old:
            if old.sha256 != digest: raise DomainError('idempotency_conflict', 'Ключ загрузки уже использован для другого изображения', status=409)
            return as_dict(old)
        root.mkdir(parents=True, exist_ok=True)
        target = root / (str(identifier) + '.png')
        with NamedTemporaryFile(dir=root, delete=False) as temporary:
            path = Path(temporary.name)
            try:
                temporary.write(encoded); temporary.flush()
                os.replace(path, target); target.chmod(0o600)
            finally: path.unlink(missing_ok=True)
        row = CatalogImage(id=identifier, sha256=digest, size=len(encoded)); db.add(row); db.flush()
        return as_dict(row)


@router.get('/{identifier}', dependencies=[Depends(require_admin)])
def download(identifier: UUID, request: Request, db: Session = Depends(get_session)):
    get_entity(db, CatalogImage, identifier)
    path = Path(request.app.state.settings.attachment_root) / 'catalog' / (str(identifier) + '.png')
    if not path.is_file(): raise DomainError('not_found', 'Изображение недоступно', status=404)
    return FileResponse(path, media_type='image/png', headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, max-age=3600'})
