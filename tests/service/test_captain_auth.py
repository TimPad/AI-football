from uuid import uuid4
from datetime import timedelta
from sqlalchemy.orm import Session
from .captain_helpers import captain,configure_mail,delivered_token,PASSWORD

AUTH='/api/v1/captain/auth'
def test_verify_separate_session_csrf_and_reset(client):
    c,_=captain(client.app)
    assert c.get(AUTH+'/me').json()['email']=='captain@example.test'
    assert 'af_captain_session' in c.cookies and 'af_session' not in c.cookies
    assert c.get('/api/v1/teams').status_code==401
    assert c.post(AUTH+'/logout',headers={'X-CSRF-Token':'wrong'}).status_code==403
    known=c.post(AUTH+'/password-reset',json={'email':'captain@example.test'});token=delivered_token(client.app)
    unknown=c.post(AUTH+'/password-reset',json={'email':'absent@example.test'});assert known.status_code==unknown.status_code==202 and known.json()==unknown.json()
    body={'request_id':str(uuid4()),'token':token,'password':'replacement-test-password'}
    assert c.post(AUTH+'/password-reset/complete',json=body).status_code==200
    assert c.post(AUTH+'/password-reset/complete',json=body).status_code==200
    assert c.get(AUTH+'/me').status_code==401
    assert c.post(AUTH+'/login',json={'email':'captain@example.test','password':PASSWORD}).status_code==401
    assert c.post(AUTH+'/login',json={'email':'captain@example.test','password':body['password']}).status_code==200

def test_expired_verification_transport_and_rate_limit(client):
    assert client.post(AUTH+'/register',json={'email':'a@example.test','display_name':'A','password':PASSWORD}).status_code==503
    c,token=captain(client.app,verify=False)
    assert c.post(AUTH+'/login',json={'email':'captain@example.test','password':PASSWORD}).status_code==401
    from aifootball.service.captains.models import CaptainToken
    with Session(client.app.state.engine) as db,db.begin():
        for row in db.query(CaptainToken):row.expires_at-=timedelta(days=2)
    assert c.post(AUTH+'/verify',json={'token':token}).status_code==422
    for _ in range(9):c.post(AUTH+'/login',json={'email':'captain@example.test','password':'incorrect'})
    assert c.post(AUTH+'/login',json={'email':'captain@example.test','password':'incorrect'}).status_code==429

def test_email_not_verified_before_token_and_no_secrets_in_api_or_outbox(client):
    c,token=captain(client.app,verify=False)
    from aifootball.service.captains.models import CaptainAccount,MailOutbox
    with Session(client.app.state.engine) as db:
        assert db.query(CaptainAccount).one().verified_at is None
        assert db.query(MailOutbox).one().encrypted_payload is None
    body={'request_id':str(uuid4()),'token':token}
    assert c.post(AUTH+'/verify',json=body).status_code==200
    assert c.post(AUTH+'/verify',json=body).status_code==200
    assert c.post(AUTH+'/verify',json={**body,'request_id':str(uuid4())}).status_code==409
    assert c.get(AUTH+'/outbox').status_code in {404,405}

def test_encrypted_outbox_retries_with_stable_message_id_then_erases_payload(client):
    from cryptography.fernet import Fernet
    from aifootball.service.captains.mail import deliver_pending
    from aifootball.service.captains.models import MailOutbox
    import json
    configure_mail(client.app);sender=client.app.state.mail_sender
    class Failing:
        def send(self,message,key):raise OSError('synthetic failure')
    client.app.state.mail_sender=Failing()
    assert client.post(AUTH+'/register',json={'email':'retry@example.test','password':PASSWORD,'display_name':'Капитан'}).status_code==202
    with Session(client.app.state.engine) as db:
        row=db.query(MailOutbox).one();identifier=str(row.id)
        assert 'retry@example.test' not in row.encrypted_payload
        message=json.loads(Fernet(client.app.state.settings.captain_mail_key).decrypt(row.encrypted_payload))
        assert '#token=' in message['url'] and '?token=' not in message['url']
    assert deliver_pending(client.app)==0
    with Session(client.app.state.engine) as db,db.begin():
        row=db.query(MailOutbox).one();assert row.attempts==1 and row.encrypted_payload
        row.next_attempt_at-=timedelta(hours=1)
    client.app.state.mail_sender=sender;assert deliver_pending(client.app)==1
    assert sender.messages[0]['key']==identifier
    with Session(client.app.state.engine) as db:assert db.query(MailOutbox).one().encrypted_payload is None
