from uuid import uuid4

def test_inline_new_players_are_atomic_and_retry_safe(admin_client,match_factory,send_command):
    from .test_confirmation import finish
    match=finish(send_command,match_factory());match=send_command(match,'confirm',{'acknowledge_incomplete':True}).json();eid=match['home_entry_id'];roster=admin_client.get(f'/api/v1/entries/{eid}/players').json();pid=str(uuid4())
    body={'request_id':str(uuid4()),'expected_revision':roster['revision'],'players':[{'player_id':p['player_id'],'shirt_number':p['shirt_number']} for p in roster['players']]+[{'player_id':pid,'shirt_number':'99'}],'new_players':[{'player_id':pid,'name':'Новый в заявке','revision':0}]}
    r=admin_client.put(f'/api/v1/entries/{eid}/roster',json=body);assert r.status_code==200,r.text
    assert admin_client.put(f'/api/v1/entries/{eid}/roster',json=body).json()==r.json()
    assert len(r.json()['players'])==len(roster['players'])+1
    assert admin_client.get('/api/v1/matches/'+match['id']).json()['lineup']==match['lineup']
    # Failed duplicate number does not leave a global person behind.
    another=str(uuid4());body={**body,'request_id':str(uuid4()),'expected_revision':r.json()['revision'],'players':body['players']+[{'player_id':another,'shirt_number':'99'}],'new_players':[{'player_id':another,'name':'Откат создания','revision':0}]}
    assert admin_client.put(f'/api/v1/entries/{eid}/roster',json=body).status_code==422
    assert admin_client.get('/api/v1/players/'+another).status_code==404
