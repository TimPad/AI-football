def test_latest_confirmed_id_changes_only_when_a_new_version_is_confirmed(admin_client,match_factory,send_command):
    from .test_confirmation import finish
    m=finish(send_command,match_factory())
    result=send_command(m,'confirm',{'acknowledge_incomplete':True});assert result.status_code==200,result.text;m=result.json()
    first=admin_client.get(f"/api/v1/matches/{m['id']}/versions").json()['items'][0]
    assert m['latest_confirmed_version_id']==first['id']
    m=send_command(m,'publish',{'version_id':first['id']}).json()
    m=send_command(m,'reopen',{}).json();assert m['latest_confirmed_version_id']==m['published_version_id']
    m=send_command(m,'confirm',{'acknowledge_incomplete':True}).json()
    assert m['latest_confirmed_version_id']!=m['published_version_id']
    listing=admin_client.get(f"/api/v1/tournaments/{m['tournament_id']}/matches").json()['items'][0]
    assert listing['latest_confirmed_version_id']==m['latest_confirmed_version_id']
