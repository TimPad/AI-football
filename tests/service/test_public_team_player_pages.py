from uuid import uuid4
from .test_confirmation import finish

def publish(admin,send,m):
    m=finish(send,m);r=send(m,'confirm',{'acknowledge_incomplete':True});assert r.status_code==200,r.text;m=r.json()
    v=admin.get(f"/api/v1/matches/{m['id']}/versions").json()['items'][0]
    r=send(m,'publish',{'version_id':v['id']});assert r.status_code==200,r.text
    return r.json()

def test_public_team_exposes_no_roster_until_protocol_publication(admin_client,match_factory,send_command):
    m=match_factory();tid=m['tournament_id'];team_id=m['home']['team_id'];person=next(p for p in m['lineup'] if p['side']=='home');pid=person['player_id']
    url=f'/api/v1/public/tournaments/{tid}/teams/{team_id}'
    r=admin_client.get(url);assert r.status_code==200,r.text
    assert r.json()['players']['total']==0
    assert admin_client.get(f'/api/v1/public/players/{pid}?tournament_id={tid}').status_code==404
    m=publish(admin_client,send_command,m)
    profile=admin_client.get(f'/api/v1/public/players/{pid}?tournament_id={tid}');assert profile.status_code==200,profile.text
    assert profile.json()['display_name']==person['display_name']
    assert profile.json()['appearances']['total']==1
    team=admin_client.get(url).json();assert pid in {p['player_id'] for p in team['players']['items']}
    assert not {'birth_date','height_cm','weight_kg','photo_id','revision','draft','entry_player_id'} & set(team['players']['items'][0])
    assert admin_client.get(f'/api/v1/public/tournaments/{tid}/teams').json()['total']==2
    assert admin_client.get(f'/api/v1/public/tournaments/{tid}/matches?team_id={team_id}').json()['total']==1

def test_public_player_names_and_history_come_from_snapshots_not_catalogue(admin_client,match_factory,send_command):
    first=publish(admin_client,send_command,match_factory());tid=first['tournament_id'];p=next(p for p in first['lineup'] if p['side']=='home');pid=p['player_id']
    response=admin_client.patch('/api/v1/players/'+pid,json={'name':'Новое опубликованное имя','birth_date':'2000-01-01','height_cm':199,'weight_kg':99});assert response.status_code==200
    data={k:first[k] for k in ['home_entry_id','away_entry_id','regulation_id','hall_id']};data['scheduled_at']='2026-11-01T19:00:00+03:00'
    r=admin_client.post(f'/api/v1/tournaments/{tid}/matches',json=data);assert r.status_code==201,r.text
    second=r.json();second=send_command(second,'set_lineup',{'players':[{'entry_player_id':q['entry_player_id'],'side':q['side']} for q in first['lineup']]}).json();second=publish(admin_client,send_command,second)
    admin_client.patch('/api/v1/players/'+pid,json={'name':'PRIVATE не опубликовано'})
    result=admin_client.get(f'/api/v1/public/players/{pid}?tournament_id={tid}');assert result.status_code==200,result.text;body=result.json()
    assert body['display_name']=='Новое опубликованное имя'
    assert {a['display_name'] for a in body['appearances']['items']}=={p['display_name'],'Новое опубликованное имя'}
    assert 'PRIVATE' not in result.text and '2000-01-01' not in result.text
    assert body['appearances']['total']==2

def test_private_or_archived_tournaments_and_unpublished_people_are_not_public(admin_client,match_factory,send_command):
    m=publish(admin_client,send_command,match_factory());tid=m['tournament_id'];pid=m['lineup'][0]['player_id'];team=m['home']['team_id']
    assert admin_client.get(f'/api/v1/public/tournaments/{tid}/teams/{uuid4()}').status_code==404
    assert admin_client.get(f'/api/v1/public/players/{uuid4()}?tournament_id={tid}').status_code==404
    current=admin_client.get('/api/v1/tournaments/'+tid).json();admin_client.patch('/api/v1/tournaments/'+tid,json={'expected_revision':current['revision'],'visibility':'draft'})
    for path in [f'/public/tournaments/{tid}/teams',f'/public/tournaments/{tid}/teams/{team}',f'/public/players/{pid}?tournament_id={tid}',f'/public/players/{pid}']:
        assert admin_client.get('/api/v1'+path).status_code==404
    current=admin_client.get('/api/v1/tournaments/'+tid).json();admin_client.patch('/api/v1/tournaments/'+tid,json={'expected_revision':current['revision'],'visibility':'public','archived':True})
    assert admin_client.get(f'/api/v1/public/players/{pid}').status_code==404
