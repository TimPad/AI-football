"""Encrypted outbox; only a configured worker transmits production mail."""
import json
from datetime import timedelta
from email.message import EmailMessage
import smtplib
from sqlalchemy import select,or_
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet
from aifootball.service.db import utcnow
from aifootball.service.errors import DomainError
from aifootball.service.captains.models import MailOutbox

class SMTPMailSender:
    def __init__(self,settings):self.settings=settings
    def send(self,message,key):
        s=self.settings;mail=EmailMessage();mail['From']=s.captain_mail_from;mail['To']=message['to'];mail['Subject']=message['subject'];mail['Message-ID']=f'<{key}@aifootball.local>'
        mail.set_content(message['text']+'\n\n'+message['url'])
        with smtplib.SMTP(s.captain_smtp_host,s.captain_smtp_port,timeout=5) as smtp:
            smtp.starttls()
            if s.captain_smtp_user:smtp.login(s.captain_smtp_user,s.captain_smtp_password)
            smtp.send_message(mail)

def sender(app):
    if hasattr(app.state,'mail_sender'):return app.state.mail_sender
    s=app.state.settings
    return SMTPMailSender(s) if s.captain_smtp_host and s.captain_mail_from else None

def require_transport(app):
    try:Fernet(app.state.settings.captain_mail_key)
    except (ValueError,TypeError):raise DomainError('mail_unavailable','Почта кабинета команды пока не подключена. Обратитесь к организатору.',status=503)
    if sender(app) is None:raise DomainError('mail_unavailable','Почта кабинета команды пока не подключена. Обратитесь к организатору.',status=503)

def enqueue(db,app,kind,email,token,expires):
    require_transport(app)
    route={'verify':'verify','reset':'password-reset','invitation':'invitation'}[kind]
    message={'to':email,'subject':{'verify':'Подтвердите email — AI Football','reset':'Восстановление доступа — AI Football','invitation':'Приглашение капитану — AI Football'}[kind],
             'text':'Откройте ссылку для продолжения. Если вы не запрашивали это письмо, его можно проигнорировать.',
             'url':app.state.settings.allowed_origin.rstrip('/')+'/captain/'+route+'#token='+token}
    encrypted=Fernet(app.state.settings.captain_mail_key).encrypt(json.dumps(message,ensure_ascii=False).encode()).decode()
    db.add(MailOutbox(kind=kind,encrypted_payload=encrypted,expires_at=expires,next_attempt_at=utcnow()))

def deliver_pending(app,limit=50):
    transport=sender(app)
    if transport is None:return 0
    count=0
    # Stable message IDs allow a transport to deduplicate retries. SMTP is at least once.
    for _ in range(limit):
        with Session(app.state.engine) as db,db.begin():
            now=utcnow();row=db.scalar(select(MailOutbox).where(MailOutbox.encrypted_payload.is_not(None),or_(MailOutbox.next_attempt_at<=now,MailOutbox.expires_at<=now)).order_by(MailOutbox.created_at).with_for_update(skip_locked=True).limit(1))
            if row is None:break
            if row.expires_at<=now:row.encrypted_payload=None;row.error_code='expired';continue
            try:
                message=json.loads(Fernet(app.state.settings.captain_mail_key).decrypt(row.encrypted_payload.encode()))
                transport.send(message,str(row.id))
            except Exception:
                row.attempts+=1;row.error_code='delivery_failed';row.next_attempt_at=now+timedelta(seconds=min(3600,60*2**min(row.attempts,6)))
            else:row.sent_at=now;row.encrypted_payload=None;row.error_code=None;count+=1
    return count

def main():
    from aifootball.service.app import create_app
    app=create_app()
    try:print(f'Delivered: {deliver_pending(app)}')
    finally:app.state.engine.dispose()
if __name__=='__main__':main()
