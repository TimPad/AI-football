from datetime import timedelta
from secrets import token_urlsafe
import hmac,hashlib,json
from uuid import uuid4
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError,InvalidHashError
from fastapi import APIRouter,Request,Response,Depends
from sqlalchemy import select,delete
from sqlalchemy.orm import Session
from aifootball.service.auth.security import check_origin,token_hash
from aifootball.service.db import utcnow
from aifootball.service.errors import DomainError
from aifootball.service.halls.operations import lock_request
from aifootball.service.captains.models import CaptainAccount,CaptainSession,CaptainToken,CaptainAuthCommand
from aifootball.service.captains.schemas import Register,Login,TokenInput,ResetComplete,EmailInput,MessageView,CaptainSessionView
from aifootball.service.captains.security import current_session,require_captain_csrf,throttle
from aifootball.service.captains.mail import require_transport,enqueue

router=APIRouter(prefix='/captain/auth');hasher=PasswordHasher();DUMMY=hasher.hash(token_urlsafe(32))
MESSAGE={'message':'Если адрес подходит для продолжения, на него будет отправлено письмо.'}

def digest(settings,data):
    return hmac.new(settings.captain_mail_key.encode(),json.dumps(data.model_dump(mode='json'),sort_keys=True).encode(),hashlib.sha256).hexdigest()
def issue_token(db,app,account,purpose,*,password_hash=None,display_name=None):
    token=token_urlsafe(32);expires=utcnow()+({'verify':timedelta(hours=24),'reset':timedelta(minutes=30)}[purpose])
    db.add(CaptainToken(account_id=account.id,purpose=purpose,registration_password_hash=password_hash,registration_display_name=display_name,token_hash=token_hash(token),security_revision=account.security_revision,expires_at=expires))
    enqueue(db,app,purpose,account.email,token,expires)

@router.post('/register',response_model=MessageView,status_code=202)
def register(data:Register,request:Request):
    check_origin(request,required=True);require_transport(request.app);throttle(request,'register',data.email,5)
    hashed=digest(request.app.state.settings,data)
    with Session(request.app.state.engine) as db,db.begin():
        lock_request(db,data.request_id);lock_request(db,email_lock_id(data.email))
        prior=db.get(CaptainAuthCommand,data.request_id)
        if prior:
            if prior.request_hash!=hashed:raise DomainError('idempotency_conflict','Ключ отправки уже использован',status=409)
            return prior.response
        password_hash=hasher.hash(data.password)
        account=db.scalar(select(CaptainAccount).where(CaptainAccount.email==data.email))
        if account is None:
            account=CaptainAccount(email=data.email,display_name=data.display_name.strip(),password_hash=password_hash);db.add(account);db.flush()
        if account.active and account.verified_at is None:issue_token(db,request.app,account,'verify',password_hash=password_hash,display_name=data.display_name.strip())
        db.add(CaptainAuthCommand(request_id=data.request_id,request_hash=hashed,response=MESSAGE))
    return MESSAGE

def email_lock_id(email):
    from uuid import UUID
    return UUID(bytes=hashlib.sha256(email.encode()).digest()[:16])

def consume(db,request,data,purpose):
    token=db.scalar(select(CaptainToken).where(CaptainToken.token_hash==token_hash(data.token),CaptainToken.purpose==purpose).with_for_update())
    hashed=digest(request.app.state.settings,data)
    if token is None:raise DomainError('token','Ссылка недействительна или устарела',status=422)
    if token.used_at:
        if token.used_request_id==data.request_id and hmac.compare_digest(token.used_hash,hashed):return None
        raise DomainError('token_used','Ссылка уже использована',status=409)
    account=db.scalar(select(CaptainAccount).where(CaptainAccount.id==token.account_id).with_for_update())
    if token.expires_at<=utcnow() or not account.active or token.security_revision!=account.security_revision:raise DomainError('token','Ссылка недействительна или устарела',status=422)
    if purpose=='verify':
        if account.verified_at is not None or not token.registration_password_hash or not token.registration_display_name:
            raise DomainError('token','Ссылка устарела. Повторите регистрацию и используйте новое письмо.',status=422)
        account.password_hash=token.registration_password_hash
        account.display_name=token.registration_display_name
        token.registration_password_hash=None;token.registration_display_name=None
    token.used_at=utcnow();token.used_request_id=data.request_id;token.used_hash=hashed
    return account

@router.post('/verify',response_model=MessageView)
def verify(data:TokenInput,request:Request):
    check_origin(request,required=True);throttle(request,'verify',limit=20)
    with Session(request.app.state.engine) as db,db.begin():
        account=consume(db,request,data,'verify')
        if account:
            account.verified_at=utcnow();account.security_revision+=1
    return {'message':'Email подтверждён. Войдите в кабинет команды.'}

@router.post('/login',response_model=CaptainSessionView)
def login(data:Login,request:Request,response:Response):
    check_origin(request,required=True);throttle(request,'login',data.email)
    with Session(request.app.state.engine) as db,db.begin():
        account=db.scalar(select(CaptainAccount).where(CaptainAccount.email==data.email).with_for_update())
        try:valid=hasher.verify(account.password_hash if account else DUMMY,data.password)
        except (VerificationError,InvalidHashError):valid=False
        if not valid or account is None or not account.active or not account.verified_at:raise DomainError('credentials','Неверный email или пароль, либо email ещё не подтверждён.',status=401)
        token,csrf=token_urlsafe(32),token_urlsafe(32)
        db.add(CaptainSession(token_hash=token_hash(token),account_id=account.id,csrf_token=csrf,expires_at=utcnow()+timedelta(hours=request.app.state.settings.session_hours)))
        result={'id':account.id,'email':account.email,'display_name':account.display_name,'csrf_token':csrf}
    response.set_cookie('af_captain_session',token,httponly=True,samesite='lax',path='/',secure=request.app.state.settings.secure_cookies,max_age=request.app.state.settings.session_hours*3600)
    return result

@router.get('/me',response_model=CaptainSessionView)
def me(request:Request):
    account,session=current_session(request)
    return {'id':account.id,'email':account.email,'display_name':account.display_name,'csrf_token':session.csrf_token}

@router.post('/logout',status_code=204)
def logout(request:Request,response:Response,account=Depends(require_captain_csrf)):
    with Session(request.app.state.engine) as db,db.begin():db.execute(delete(CaptainSession).where(CaptainSession.token_hash==token_hash(request.cookies['af_captain_session'])))
    response.delete_cookie('af_captain_session',path='/')

@router.post('/password-reset',response_model=MessageView,status_code=202)
def reset(data:EmailInput,request:Request):
    check_origin(request,required=True);require_transport(request.app);throttle(request,'reset',data.email,5)
    with Session(request.app.state.engine) as db,db.begin():
        account=db.scalar(select(CaptainAccount).where(CaptainAccount.email==data.email))
        if account and account.active and account.verified_at:issue_token(db,request.app,account,'reset')
    return MESSAGE

@router.post('/password-reset/complete',response_model=MessageView)
def reset_complete(data:ResetComplete,request:Request):
    check_origin(request,required=True);throttle(request,'reset-complete',limit=20)
    with Session(request.app.state.engine) as db,db.begin():
        account=consume(db,request,data,'reset')
        if account:
            account.password_hash=hasher.hash(data.password);account.security_revision+=1
            db.execute(delete(CaptainSession).where(CaptainSession.account_id==account.id))
    return {'message':'Пароль обновлён. Войдите снова.'}
