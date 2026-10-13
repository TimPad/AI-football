def test_match_keeps_roster_and_rules_snapshot(admin_client,match_factory,regulation_data):
    m=match_factory(); player=m['lineup'][0]
    assert admin_client.patch(f"/api/v1/players/{player['player_id']}",json={'name':'Новое имя'}).status_code==200
    admin_client.post(f"/api/v1/tournaments/{m['tournament_id']}/regulations",json={
        'variant_name':'Группа','rules':{**regulation_data,'periods_s':[900,900]}})
    saved=admin_client.get(f"/api/v1/matches/{m['id']}").json()
    assert saved['lineup'][0]['display_name']==player['display_name']
    assert saved['regulation']['rules']['periods_s']==[1200,1200]


def test_foreign_match_links_and_naive_dates(admin_client,match_factory):
    a,b=match_factory(),match_factory()
    data={'home_entry_id':a['home_entry_id'],'away_entry_id':b['away_entry_id'],
          'regulation_id':a['regulation']['id'],'scheduled_at':'2026-10-20T18:00:00+03:00'}
    url=f"/api/v1/tournaments/{a['tournament_id']}/matches"
    assert admin_client.post(url,json=data).status_code==422
    data['away_entry_id']=a['away_entry_id']; data['scheduled_at']='2026-10-20T18:00:00'
    assert admin_client.post(url,json=data).status_code==422


def test_commands_retry_and_conflict(admin_client,match_factory,send_command):
    from uuid import uuid4
    m=match_factory(); key=str(uuid4())
    first=send_command(m,'update_match',{'venue_label':'Зал'},key)
    second=send_command(m,'update_match',{'venue_label':'Зал'},key)
    assert first.status_code==second.status_code==200
    assert first.json()==second.json()
    assert first.json()['id']==m['id']
    assert send_command(m,'set_status',{'status':'live'}).status_code==409


def test_regulation_apply_is_atomic(admin_client,match_factory,send_command,regulation_data):
    from uuid import uuid4
    a=match_factory(); tid=a['tournament_id']
    b=admin_client.post(f'/api/v1/tournaments/{tid}/matches',json={
        'home_entry_id':a['home_entry_id'],'away_entry_id':a['away_entry_id'],
        'regulation_id':a['regulation']['id'],'scheduled_at':'2026-10-21T18:00:00+03:00'}).json()
    new=admin_client.post(f'/api/v1/tournaments/{tid}/regulations',json={
        'variant_name':'Группа','rules':{**regulation_data,'periods_s':[900,900]}}).json()
    url=f"/api/v1/tournaments/{tid}/regulations/{new['id']}"
    preview=admin_client.post(url+'/preview',json={'match_ids':[a['id'],b['id']]})
    assert preview.status_code==200
    assert send_command(b,'update_match',{'venue_label':'Изменён'}).status_code==200
    payload={'request_id':str(uuid4()),'matches':[{'id':x['id'],'expected_revision':x['revision']} for x in [a,b]]}
    assert admin_client.post(url+'/apply',json=payload).status_code==409
    assert admin_client.get(f"/api/v1/matches/{a['id']}").json()['regulation']['id']==a['regulation']['id']


def test_match_status_and_null_date(admin_client,match_factory,send_command):
    m=match_factory()
    assert send_command(m,'update_match',{'scheduled_at':None}).status_code==422
    live=send_command(m,'set_status',{'status':'live'}); assert live.status_code==200
    ended=send_command(live.json(),'set_status',{'status':'ended'}); assert ended.status_code==200
    assert send_command(ended.json(),'set_status',{'status':'live'}).status_code==422
    assert len(admin_client.get(f"/api/v1/tournaments/{m['tournament_id']}/matches?day=2026-10-20").json()['items'])==1


def test_lineup_rejects_wrong_side_and_archived_player(admin_client,match_factory,send_command):
    m=match_factory(); member=m['lineup'][0]
    wrong='away' if member['side']=='home' else 'home'
    assert send_command(m,'set_lineup',{'players':[{'entry_player_id':member['entry_player_id'],'side':wrong}]}).status_code==422
    admin_client.patch(f"/api/v1/players/{member['player_id']}",json={'archived':True})
    assert send_command(m,'set_lineup',{'players':[{'entry_player_id':member['entry_player_id'],'side':member['side']}]}).status_code==422
