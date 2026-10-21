from urllib.parse import urlparse,parse_qs
from uuid import uuid4
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet

PASSWORD='synthetic-captain-password'
class MemorySender:
    def __init__(self):self.messages=[]
    def send(self,message,key):
        if not any(m['key']==key for m in self.messages):self.messages.append({**message,'key':key})

def configure_mail(app):
    app.state.settings.captain_mail_key=Fernet.generate_key().decode()
    app.state.mail_sender=MemorySender()

def delivered_token(app):
    from aifootball.service.captains.mail import deliver_pending
    deliver_pending(app)
    return parse_qs(urlparse(app.state.mail_sender.messages[-1]['url']).fragment)['token'][0]

def captain(app,email='captain@example.test',verify=True):
    if not hasattr(app.state,'mail_sender'):configure_mail(app)
    c=TestClient(app);c.headers['Origin']=app.state.settings.allowed_origin
    result=c.post('/api/v1/captain/auth/register',json={'email':email,'display_name':'Капитан','password':PASSWORD,'request_id':str(uuid4())})
    assert result.status_code==202,result.text
    token=delivered_token(app)
    if verify:
        r=c.post('/api/v1/captain/auth/verify',json={'token':token,'request_id':str(uuid4())});assert r.status_code==200,r.text
        login=c.post('/api/v1/captain/auth/login',json={'email':email,'password':PASSWORD});assert login.status_code==200,login.text
        c.headers['X-CSRF-Token']=login.json()['csrf_token']
    return c,token
