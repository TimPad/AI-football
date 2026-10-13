def test_catalog_archive_and_identity(admin_client,tournament_factory):
    team=admin_client.post('/api/v1/teams',json={'name':'  Север  '})
    assert team.status_code==201
    assert team.json()['name']=='Север'
    tid=tournament_factory()['id']; url=f'/api/v1/tournaments/{tid}/entries'
    assert admin_client.post(url,json={'team_id':team.json()['id']}).status_code==201
    assert admin_client.post(url,json={'team_id':team.json()['id']}).status_code==409
    assert admin_client.patch(f"/api/v1/teams/{team.json()['id']}",json={'archived':True}).status_code==200
    other=tournament_factory()['id']
    assert admin_client.post(f'/api/v1/tournaments/{other}/entries',json={'team_id':team.json()['id']}).status_code==422


def test_duplicate_active_number_rejected(admin_client,tournament_factory):
    t=tournament_factory(); team=admin_client.post('/api/v1/teams',json={'name':'Север'}).json()
    entry=admin_client.post(f"/api/v1/tournaments/{t['id']}/entries",json={'team_id':team['id']}).json()
    players=[admin_client.post('/api/v1/players',json={'name':n}).json() for n in ['Игрок1','Игрок2']]
    url=f"/api/v1/entries/{entry['id']}/players"
    payload={'expected_revision':0,'players':[{'player_id':p['id'],'shirt_number':'7'} for p in players]}
    assert admin_client.put(url,json=payload).status_code==422
    payload['players'][1]['shirt_number']=None
    assert admin_client.put(url,json=payload).status_code==200
