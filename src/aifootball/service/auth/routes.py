from datetime import timedelta
from secrets import token_urlsafe
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session
from aifootball.service.auth.models import Admin, AdminSession, LoginAttempt
from aifootball.service.auth.schemas import Login
from aifootball.service.auth.security import check_origin, token_hash, current_session, require_csrf
from aifootball.service.db import utcnow
from aifootball.service.errors import DomainError

from aifootball.service.views import SessionView

router = APIRouter(prefix='/auth')
# Равная стоимость хеширования для неизвестного пользователя.
_hasher = PasswordHasher()
_dummy_hash = _hasher.hash(token_urlsafe(32))


@router.post('/login',response_model=SessionView)
def login(data: Login, request: Request, response: Response):
    check_origin(request, required=True)
    now = utcnow()
    ip = request.client.host if request.client else 'unknown'
    name = data.login.strip().lower()
    with Session(request.app.state.engine) as db:
        count = db.scalar(select(func.count()).select_from(LoginAttempt).where(
            LoginAttempt.login == name, LoginAttempt.ip == ip,
            LoginAttempt.failed_at > now - timedelta(minutes=10)))
        if count >= 10:
            raise DomainError('rate_limit', 'Слишком много попыток. Попробуйте через 10 минут', status=429)
        admin = db.scalar(select(Admin).where(Admin.login == name))
        try:
            valid = _hasher.verify(admin.password_hash if admin else _dummy_hash, data.password)
        except (VerifyMismatchError, InvalidHashError):
            valid = False
        if not valid or admin is None or not admin.active:
            db.add(LoginAttempt(login=name, ip=ip))
            db.commit()
            raise DomainError('credentials', 'Неверный логин или пароль', status=401)
        token, csrf = token_urlsafe(32), token_urlsafe(32)
        db.add(AdminSession(token_hash=token_hash(token), admin_id=admin.id, csrf_token=csrf,
                            expires_at=now + timedelta(hours=request.app.state.settings.session_hours)))
        db.execute(delete(LoginAttempt).where(LoginAttempt.failed_at < now - timedelta(days=1)))
        db.commit()
        response.set_cookie('af_session', token, httponly=True, samesite='lax', path='/',
                            secure=request.app.state.settings.secure_cookies,
                            max_age=request.app.state.settings.session_hours * 3600)
        return {'id': str(admin.id), 'login': admin.login, 'csrf_token': csrf}


@router.get('/me',response_model=SessionView)
def me(request: Request):
    admin, auth = current_session(request)
    return {'id': str(admin.id), 'login': admin.login, 'csrf_token': auth.csrf_token}


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response, admin=Depends(require_csrf)):
    with Session(request.app.state.engine) as db:
        db.execute(delete(AdminSession).where(AdminSession.token_hash == token_hash(request.cookies['af_session'])))
        db.commit()
    response.delete_cookie('af_session', path='/')
