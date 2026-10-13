from hashlib import sha256
from secrets import compare_digest
from sqlalchemy.orm import Session
from fastapi import Request
from aifootball.service.auth.models import Admin, AdminSession
from aifootball.service.db import utcnow
from aifootball.service.errors import DomainError


def token_hash(value):
    return sha256(value.encode()).hexdigest()


def check_origin(request, *, required=False):
    origin = request.headers.get('origin')
    if (required and not origin) or (origin and origin != request.app.state.settings.allowed_origin):
        raise DomainError('origin', 'Этот источник запроса не разрешён', status=403)


def current_session(request):
    token = request.cookies.get('af_session')
    if not token:
        raise DomainError('unauthorized', 'Войдите в кабинет', status=401)
    with Session(request.app.state.engine) as db:
        auth = db.get(AdminSession, token_hash(token))
        if auth is None or auth.expires_at <= utcnow():
            raise DomainError('unauthorized', 'Сессия истекла. Войдите снова', status=401)
        admin = db.get(Admin, auth.admin_id)
        if admin is None or not admin.active:
            raise DomainError('unauthorized', 'Войдите в кабинет', status=401)
        db.expunge(admin)
        db.expunge(auth)
        return admin, auth


def require_admin(request: Request):
    return current_session(request)[0]


def require_csrf(request: Request):
    check_origin(request)
    admin, auth = current_session(request)
    if not compare_digest(request.headers.get('x-csrf-token', ''), auth.csrf_token):
        raise DomainError('csrf', 'Обновите сессию и повторите сохранение', status=403)
    return admin
