from uuid import uuid4
from sqlalchemy.orm import Session
from .captain_helpers import captain,configure_mail,delivered_token

def test_invitation_email_match_repeat_and_revocation(admin_client):
    configure_mail(admin_client.app);c,_=captain(admin_client.app);other,_=captain(admin_client.app,'other@example.test')
    team=admin_client.post('/api/v1/teams',json={'name':'Север'}).json()
    url=f"/api/v1/teams/{team['id']}/captain-invitations"
    result=admin_client.post(url,json={'email':'captain@example.test','request_id':str(uuid4())});assert result.status_code==201,result.text
    token=delivered_token(admin_client.app);body={'token':token,'request_id':str(uuid4())}
    assert other.post('/api/v1/captain/invitations/accept',json=body).status_code==404
    accepted=c.post('/api/v1/captain/invitations/accept',json=body);assert accepted.status_code==200,accepted.text
    assert c.post('/api/v1/captain/invitations/accept',json=body).json()==accepted.json()
    assert c.get('/api/v1/captain/teams').json()['items'][0]['id']==team['id']
    assert other.get(f"/api/v1/captain/teams/{team['id']}").status_code==404
    grant=accepted.json();r=admin_client.post(f"/api/v1/teams/{team['id']}/captain-grants/{grant['id']}/revoke",json={'request_id':str(uuid4()),'reason':'Смена капитана'})
    assert r.status_code==200,r.text
    assert c.get(f"/api/v1/captain/teams/{team['id']}").status_code==404

def test_revoked_invitation_does_not_grant_access(admin_client):
    configure_mail(admin_client.app);c,_=captain(admin_client.app)
    team=admin_client.post('/api/v1/teams',json={'name':'Север'}).json();base=f"/api/v1/teams/{team['id']}/captain-invitations"
    invite=admin_client.post(base,json={'email':'captain@example.test','request_id':str(uuid4())}).json();token=delivered_token(admin_client.app)
    assert admin_client.post(base+'/'+invite['id']+'/revoke',json={'request_id':str(uuid4()),'reason':'Отозвано'}).status_code==200
    assert c.post('/api/v1/captain/invitations/accept',json={'token':token,'request_id':str(uuid4())}).status_code==404

def test_expiry_one_owner_and_explicit_transfer(admin_client):
    from datetime import timedelta
    from aifootball.service.captains.models import TeamCaptainInvitation,TeamCaptainGrant
    configure_mail(admin_client.app);c,_=captain(admin_client.app);other,_=captain(admin_client.app,'other@example.test')
    team=admin_client.post('/api/v1/teams',json={'name':'Север'}).json();base=f"/api/v1/teams/{team['id']}"
    admin_client.post(base+'/captain-invitations',json={'email':'captain@example.test','request_id':str(uuid4())});token=delivered_token(admin_client.app)
    with Session(admin_client.app.state.engine) as db,db.begin():db.query(TeamCaptainInvitation).one().expires_at-=timedelta(days=4)
    assert c.post('/api/v1/captain/invitations/accept',json={'token':token,'request_id':str(uuid4())}).status_code==404
    first_id=c.get('/api/v1/captain/auth/me').json()['id'];other_id=other.get('/api/v1/captain/auth/me').json()['id']
    for account,replace,status in [(first_id,False,200),(other_id,False,409),(other_id,True,200)]:
        result=admin_client.post(base+'/captain-grants',json={'request_id':str(uuid4()),'account_id':account,'replace':replace,'reason':'Передача капитанства'})
        assert result.status_code==status,result.text
    assert c.get('/api/v1/captain/teams/'+team['id']).status_code==404
    assert other.get('/api/v1/captain/teams/'+team['id']).status_code==200
    with Session(admin_client.app.state.engine) as db:assert db.query(TeamCaptainGrant).filter_by(active=True).count()==1
