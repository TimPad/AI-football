from secrets import compare_digest
from hashlib import sha256
from fastapi import Request
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from aifootball.service.db import utcnow
from aifootball.service.errors import DomainError
from aifootball.service.auth.security import token_hash,check_origin
from aifootball.service.captains.models import CaptainAccount,CaptainSession,TeamCaptainGrant,CaptainRateLimit

def current_session(request):
    token=request.cookies.get('af_captain_session')
    if not token:raise DomainError('unauthorized','Войдите в кабинет команды',status=401)
    with Session(request.app.state.engine) as db:
        session=db.get(CaptainSession,token_hash(token))
        account=db.get(CaptainAccount,session.account_id) if session else None
        if not session or session.expires_at<=utcnow() or not account or not account.active or not account.verified_at:raise DomainError('unauthorized','Войдите в кабинет команды',status=401)
        db.expunge(session);db.expunge(account);return account,session

def require_captain(request:Request):return current_session(request)[0]
def require_captain_csrf(request:Request):
    check_origin(request)
    account,session=current_session(request)
    if not compare_digest(request.headers.get('X-CSRF-Token',''),session.csrf_token):raise DomainError('csrf','Обновите сессию и повторите действие',status=403)
    return account
def require_captain_team(db,account,team_id):
    grant=db.scalar(select(TeamCaptainGrant).where(TeamCaptainGrant.account_id==account.id,TeamCaptainGrant.team_id==team_id,TeamCaptainGrant.active))
    if not grant:raise DomainError('not_found','Команда недоступна',status=404)
    return grant

def throttle(request,purpose,email='',limit=10):
    key=sha256(f'{purpose}:{email}:{request.client.host if request.client else "unknown"}'.encode()).hexdigest()
    window=int(utcnow().timestamp())//600
    with Session(request.app.state.engine) as db,db.begin():
        db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(bytes.fromhex(key)[:8],signed=True))))
        row=db.get(CaptainRateLimit,key)
        if row is None:row=CaptainRateLimit(key=key,window=window,count=0);db.add(row)
        if row.window!=window:row.window=window;row.count=0
        if row.count>=limit:raise DomainError('rate_limit','Слишком много попыток. Попробуйте через 10 минут.',status=429)
        row.count+=1
