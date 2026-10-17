from uuid import uuid4
from datetime import datetime,timezone
from .captain_helpers import captain

def team(client):
    response=client.post('/api/v1/captain/teams',json={'name':'Своя','request_id':str(uuid4()),'players':[{'player_id':str(uuid4()),'name':f'Заявочный {i}','shirt_number':str(i)} for i in [1,2]]})
    assert response.status_code==201,response.text
    return response.json()

def create_application(c,t,tid,**extra):
    r=c.post(f'/api/v1/captain/tournaments/{tid}/applications',json={'team_id':t['id'],'request_id':str(uuid4()),**extra});assert r.status_code==201,r.text
    return r.json()

def submit(c,a):
    r=c.post(f"/api/v1/captain/applications/{a['id']}/submit",json={'request_id':str(uuid4()),'expected_revision':a['revision']});assert r.status_code==200,r.text
    return r.json()

def test_versioned_application_is_not_entry_until_accepted(admin_client,tournament_factory,regulation_data):
    c,_=captain(admin_client.app);t=team(c);tour=tournament_factory();tid=tour['id']
    admin_client.post(f'/api/v1/tournaments/{tid}/regulations',json={'variant_name':'Основной','rules':regulation_data})
    a=create_application(c,t,tid);sent=submit(c,a)
    assert admin_client.get(f'/api/v1/tournaments/{tid}/entries').json()['total']==0
    version=sent['submitted_version'];assert len(version['payload']['players'])==2
    # A later permanent roster edit does not alter the submitted version.
    c.put('/api/v1/captain/teams/'+t['id'],json={'request_id':str(uuid4()),'expected_revision':t['revision'],'name':t['name'],'players':[]})
    assert c.get(f"/api/v1/captain/applications/{a['id']}").json()['submitted_version']==version
    body={'request_id':str(uuid4()),'expected_revision':sent['revision'],'version_id':version['id'],'reason':'Проверено'}
    url=f"/api/v1/tournaments/{tid}/applications/{a['id']}/accept"
    accepted=admin_client.post(url,json=body);assert accepted.status_code==200,accepted.text
    assert admin_client.post(url,json=body).json()==accepted.json()
    entries=admin_client.get(f'/api/v1/tournaments/{tid}/entries').json()['items'];assert len(entries)==1
    assert len(admin_client.get(f"/api/v1/entries/{entries[0]['id']}/players").json()['players'])==2

def test_submission_retry_and_returned_version_remains_immutable(admin_client,tournament_factory,regulation_data):
    c,_=captain(admin_client.app);t=team(c);tour=tournament_factory();tid=tour['id'];admin_client.post(f'/api/v1/tournaments/{tid}/regulations',json={'variant_name':'Основной','rules':regulation_data})
    a=create_application(c,t,tid);body={'request_id':str(uuid4()),'expected_revision':a['revision']};url=f"/api/v1/captain/applications/{a['id']}"
    sent=c.post(url+'/submit',json=body).json();assert c.post(url+'/submit',json=body).json()==sent
    returned=admin_client.post(f"/api/v1/tournaments/{tid}/applications/{a['id']}/request-changes",json={'request_id':str(uuid4()),'expected_revision':sent['revision'],'reason':'Уточнить номер'}).json()
    players=[{'player_id':p['player_id'],'shirt_number':'9' if i==0 else p['shirt_number']} for i,p in enumerate(t['players'])]
    edited=c.put(url+'/draft',json={'request_id':str(uuid4()),'expected_revision':returned['revision'],'source_roster_revision':t['revision'],'players':players});assert edited.status_code==200,edited.text
    again=submit(c,edited.json());assert len(again['versions'])==2
    assert again['versions'][1]['payload']['players'][0]['shirt_number']!=again['versions'][0]['payload']['players'][0]['shirt_number']

def test_private_invitation_consent_closed_and_foreign_scope(admin_client,tournament_factory,regulation_data):
    c,_=captain(admin_client.app);t=team(c);tour=tournament_factory(visibility='draft');tid=tour['id']
    assert c.post(f'/api/v1/captain/tournaments/{tid}/applications',json={'team_id':t['id'],'request_id':str(uuid4())}).status_code==404
    invitation=admin_client.post(f'/api/v1/tournaments/{tid}/entry-invitations',json={'team_id':t['id'],'request_id':str(uuid4())});assert invitation.status_code==201,invitation.text
    assert admin_client.get(f'/api/v1/tournaments/{tid}/entries').json()['total']==0
    a=create_application(c,t,tid,invitation_id=invitation.json()['id'])
    r=admin_client.put(f'/api/v1/tournaments/{tid}/applications/settings',json={'request_id':str(uuid4()),'expected_revision':0,'applications_open':False,'deadline':None});assert r.status_code==200,r.text
    assert c.post(f"/api/v1/captain/applications/{a['id']}/submit",json={'request_id':str(uuid4()),'expected_revision':a['revision']}).status_code==409
    other,_=captain(admin_client.app,'other@example.test');assert other.get(f"/api/v1/captain/applications/{a['id']}").status_code==404

def test_limits_numbers_deadline_and_archive_do_not_create_entries(admin_client,tournament_factory,regulation_data):
    c,_=captain(admin_client.app);t=team(c);tour=tournament_factory();tid=tour['id']
    regulation=admin_client.post(f'/api/v1/tournaments/{tid}/regulations',json={'variant_name':'Малая заявка','rules':{**regulation_data,'tournament_roster_limit':1,'match_roster_limit':1,'players_on_pitch':1}})
    assert regulation.status_code==201,regulation.text
    a=create_application(c,t,tid);url=f"/api/v1/captain/applications/{a['id']}"
    assert c.post(url+'/submit',json={'request_id':str(uuid4()),'expected_revision':0}).status_code==422
    duplicate=[{'player_id':p['player_id'],'shirt_number':'7'} for p in t['players']]
    assert c.put(url+'/draft',json={'request_id':str(uuid4()),'expected_revision':0,'source_roster_revision':t['revision'],'players':duplicate}).status_code==422
    admin_client.put(f'/api/v1/tournaments/{tid}/applications/settings',json={'request_id':str(uuid4()),'expected_revision':0,'applications_open':True,'deadline':'2020-01-01T00:00:00Z'})
    assert c.post(url+'/submit',json={'request_id':str(uuid4()),'expected_revision':0}).status_code==409
    admin_client.patch('/api/v1/tournaments/'+tid,json={'expected_revision':1,'archived':True})
    assert c.post(url+'/submit',json={'request_id':str(uuid4()),'expected_revision':0}).status_code==409
    assert admin_client.get(f'/api/v1/tournaments/{tid}/entries').json()['total']==0

def test_existing_entry_conflict_and_approved_version_preserve_match_lineup(admin_client,match_factory):
    m=match_factory();c,_=captain(admin_client.app);account=c.get('/api/v1/captain/auth/me').json()['id'];tid=m['tournament_id'];team_id=m['home']['team_id'];entry_id=m['home_entry_id']
    old=admin_client.get('/api/v1/teams/'+team_id).json();roster=admin_client.get(f'/api/v1/entries/{entry_id}/players').json()
    profile=admin_client.put('/api/v1/teams/'+team_id+'/profile',json={'request_id':str(uuid4()),'expected_revision':old['revision'],'name':old['name'],'players':[{'player_id':p['player_id'],'revision':p['player']['revision'],'name':p['player']['name'],'shirt_number':p['shirt_number']} for p in roster['players']]}).json()
    admin_client.post(f'/api/v1/teams/{team_id}/captain-grants',json={'request_id':str(uuid4()),'account_id':account,'reason':'Тестовый капитан'})
    a=submit(c,create_application(c,profile,tid));url=f'/api/v1/tournaments/{tid}/applications/'+a['id']
    changed=admin_client.put(f'/api/v1/entries/{entry_id}/players',json={'expected_revision':roster['revision'],'players':[{'player_id':p['player_id'],'shirt_number':'9' if i==0 else p['shirt_number']} for i,p in enumerate(roster['players'])]}).json()
    assert admin_client.post(url+'/accept',json={'request_id':str(uuid4()),'expected_revision':a['revision'],'version_id':a['submitted_version']['id'],'reason':'Проверено'}).status_code==409
    returned=admin_client.post(url+'/request-changes',json={'request_id':str(uuid4()),'expected_revision':a['revision'],'reason':'Сверьте заявку'}).json()
    fresh=c.put(f"/api/v1/captain/applications/{a['id']}/draft",json={'request_id':str(uuid4()),'expected_revision':returned['revision'],'source_roster_revision':profile['revision'],'players':[{'player_id':p['player_id'],'shirt_number':p['shirt_number']} for p in changed['players']]}).json();new=submit(c,fresh)
    assert admin_client.post(url+'/accept',json={'request_id':str(uuid4()),'expected_revision':new['revision'],'version_id':new['submitted_version']['id'],'reason':'Проверено повторно'}).status_code==200
    assert admin_client.get('/api/v1/matches/'+m['id']).json()['lineup']==m['lineup']
    assert admin_client.get(f'/api/v1/tournaments/{tid}/entries').json()['total']==2
