from uuid import uuid4
from sqlalchemy.orm import Session
from .captain_helpers import captain
from test_roster_xlsx import book as workbook

def test_team_and_owner_atomic_retry_and_profile_proposal(client):
    c,_=captain(client.app);pid=str(uuid4());body={'request_id':str(uuid4()),'name':'Команда капитана','players':[{'player_id':pid,'name':'Новый игрок','shirt_number':'7'}]}
    response=c.post('/api/v1/captain/teams',json=body);assert response.status_code==201,response.text
    team=response.json();assert c.post('/api/v1/captain/teams',json=body).json()==team
    assert c.post('/api/v1/captain/teams',json={**body,'name':'Другое'}).status_code==409
    assert c.get('/api/v1/players').status_code==401
    changed=c.put('/api/v1/captain/teams/'+team['id'],json={**body,'request_id':str(uuid4()),'expected_revision':team['revision'],'players':[{'player_id':pid,'revision':0,'name':'Исправленное ФИО','shirt_number':'8'}]})
    assert changed.status_code==200,changed.text
    value=changed.json();assert value['players'][0]['player']['name']=='Новый игрок'
    assert value['players'][0]['shirt_number']=='8' and len(value['profile_proposals'])==1
    from aifootball.service.catalog.models import Player
    with Session(client.app.state.engine) as db:assert db.get(Player,pid).name=='Новый игрок'

def test_foreign_uuid_or_duplicate_number_rolls_back(client,admin_client):
    c,_=captain(client.app);foreign=admin_client.post('/api/v1/players',json={'name':'Закрытая карточка'}).json()
    for players in [[{'player_id':foreign['id'],'name':'Подмена'}],[{'player_id':str(uuid4()),'name':'Один','shirt_number':'7'},{'player_id':str(uuid4()),'name':'Два','shirt_number':'7'}]]:
        r=c.post('/api/v1/captain/teams',json={'request_id':str(uuid4()),'name':'Та же команда','players':players});assert r.status_code in {404,422},r.text
    assert c.get('/api/v1/captain/teams').json()['total']==0
    assert c.post('/api/v1/captain/teams',json={'name':'Команда','can_manage_analytics':True}).status_code==422

def test_excel_does_not_disclose_foreign_candidates_or_mutate_shared_people(admin_client):
    c,_=captain(admin_client.app);foreign=admin_client.post('/api/v1/players',json={'name':'Совпадение','birth_date':'1990-01-01'}).json()
    team=c.post('/api/v1/captain/teams',json={'name':'Своя команда','request_id':str(uuid4())}).json()
    book=workbook([['ФИО','Номер'],['Совпадение','7'],['Новый','8']])
    up=c.post('/api/v1/captain/roster-imports',data={'scope':'team','target_id':team['id']},files={'file':('Состав.xlsx',book,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert up.status_code==201,up.text
    value=up.json();url='/api/v1/captain/roster-imports/'+value['id']
    preview=c.put(url+'/preview',json={'expected_revision':0,'sheet':'Состав','mapping':{'name':0,'shirt_number':1}})
    assert preview.status_code==200,preview.text
    data=preview.json();assert not data['can_commit']
    assert foreign['id'] not in preview.text and '1990-01-01' not in preview.text
    clean=c.put(url+'/preview',json={'expected_revision':data['revision'],'sheet':'Состав','mapping':{'name':0,'shirt_number':1},'excluded_rows':[data['rows'][0]['id']]}).json()
    assert clean['can_commit']
    result=c.post(url+'/commit',json={'request_id':str(uuid4()),'expected_revision':clean['revision']});assert result.status_code==200,result.text
    assert result.json()['players_created']==1 and result.json()['links'][0]['path'].startswith('/captain/teams/')
    other,_=captain(admin_client.app,'other@example.test');assert other.get(url).status_code==404

def test_profile_decision_and_create_replay_recheck_current_grant(admin_client):
    c,_=captain(admin_client.app);pid=str(uuid4());body={'request_id':str(uuid4()),'name':'Своя команда','players':[{'player_id':pid,'name':'Первоначальное имя'}]}
    team=c.post('/api/v1/captain/teams',json=body).json();url='/api/v1/captain/teams/'+team['id']
    proposal=c.post(url+'/profile-proposals',json={'request_id':str(uuid4()),'player_id':pid,'name':'Уточнённое имя','revision':0}).json()
    decision={'request_id':str(uuid4()),'reason':'Документы проверены'}
    path=f"/api/v1/teams/{team['id']}/profile-proposals/{proposal['id']}/accept"
    result=admin_client.post(path,json=decision);assert result.status_code==200,result.text
    assert admin_client.post(path,json=decision).json()==result.json()
    assert c.get(url).json()['players'][0]['player']['name']=='Уточнённое имя'
    grant=admin_client.get(f"/api/v1/teams/{team['id']}/captain-access").json()['grants'][0]
    admin_client.post(f"/api/v1/teams/{team['id']}/captain-grants/{grant['id']}/revoke",json={'request_id':str(uuid4()),'reason':'Отозвано'})
    assert c.post('/api/v1/captain/teams',json=body).status_code==404

def test_images_are_scoped_to_uploader_or_active_team_grant(admin_client):
    from io import BytesIO
    from PIL import Image
    c,_=captain(admin_client.app);raw=BytesIO();Image.new('RGB',(2,2),'green').save(raw,format='PNG')
    image=admin_client.post('/api/v1/catalog/images',files={'file':('logo.png',raw.getvalue(),'image/png')},headers={'X-Request-ID':str(uuid4())}).json()
    assert c.post('/api/v1/captain/teams',json={'name':'Своя','logo_id':image['id']}).status_code==404
    assert c.get('/api/v1/captain/images/'+image['id']).status_code==404
    own=c.post('/api/v1/captain/images',files={'file':('logo.png',raw.getvalue(),'image/png')},headers={'X-Request-ID':str(uuid4())})
    assert own.status_code==201,own.text
    assert c.get('/api/v1/captain/images/'+own.json()['id']).status_code==200
    other,_=captain(admin_client.app,'other@example.test');assert other.get('/api/v1/captain/images/'+own.json()['id']).status_code==404
