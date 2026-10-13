def test_clock_start_resume_refresh_and_idempotent_boundary(admin_client,match_factory,send_command):
    from uuid import uuid4
    m=match_factory(); key=str(uuid4())
    first=send_command(m,'clock_start',{},key)
    assert first.status_code==200,first.text
    assert send_command(m,'clock_start',{},key).json()==first.json()
    m=first.json()
    saved=admin_client.get(f"/api/v1/matches/{m['id']}").json()
    assert saved['clock']['phase']=='running'
    assert len(saved['protocol']['events'])==1
    pause=send_command(m,'clock_pause',{}); assert pause.status_code==200
    corrected=send_command(pause.json(),'clock_set',{'elapsed_ms':12000,'reason':'Уточнение по судье'})
    assert corrected.status_code==200
    assert corrected.json()['clock']['elapsed_ms']==12000
    end=send_command(corrected.json(),'clock_end_period',{}); assert end.status_code==200
    next_period=send_command(end.json(),'clock_start',{}); assert next_period.status_code==200
    assert next_period.json()['clock']['period']==2
    assert [e['kind'] for e in next_period.json()['protocol']['events']]==['period_start','period_end','period_start']
