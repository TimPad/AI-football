from uuid import uuid4
from .test_events import event


def test_retry_goal_and_key_conflict(admin_client,match_factory,send_command):
    m=match_factory(); key=str(uuid4()); payload={'event':event()}
    first=send_command(m,'add_event',payload,key)
    assert first.status_code==200,first.text
    second=send_command(m,'add_event',payload,key)
    assert second.status_code==200 and second.json()==first.json()
    changed={'event':{**payload['event'],'side':'away'}}
    assert send_command(m,'add_event',changed,key).status_code==409
    saved=admin_client.get(f"/api/v1/matches/{m['id']}").json()
    assert len(saved['protocol']['events'])==1
    assert saved['revision']==m['revision']+1


def test_parallel_commands_only_one_wins(admin_client,match_factory):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    m=match_factory(); barrier=Barrier(2)
    def send(side):
        with TestClient(admin_client.app) as c:
            c.headers.update(admin_client.headers); c.cookies.update(admin_client.cookies)
            barrier.wait()
            return c.post(f"/api/v1/matches/{m['id']}/commands",json={'request_id':str(uuid4()),
                'expected_revision':m['revision'],'kind':'add_event','payload':{'event':event(side=side)}}).status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(send,['home','away']))==[200,409]
    saved=admin_client.get(f"/api/v1/matches/{m['id']}").json()
    assert len(saved['protocol']['events'])==1


def test_edit_cancel_goal_and_referenced_lineup(admin_client,match_factory,send_command):
    m=match_factory(); raw=event(player_id=m['lineup'][0]['player_id'],side=m['lineup'][0]['side'])
    r=send_command(m,'add_event',{'event':raw}); assert r.status_code==200
    m=r.json()
    assert send_command(m,'set_lineup',{'players':[]}).status_code==422
    edit=send_command(m,'replace_event',{'event':{**raw,'player_id':None}}); assert edit.status_code==200
    removal=send_command(edit.json(),'remove_event',{'event_id':raw['id']}); assert removal.status_code==200
    assert removal.json()['projection']['event_score']=={'home':0,'away':0}
    history=admin_client.get(f"/api/v1/matches/{m['id']}/history").json()['items']
    assert [x['body']['kind'] for x in history][:3]==['remove_event','replace_event','add_event']


def test_complete_mismatch_and_linked_penalty_cancellation(admin_client,match_factory,send_command):
    m=match_factory(); award=event('penalty_awarded'); attempt=event('penalty_attempt',penalty_id=award['id'],outcome='goal')
    scored=event(from_penalty=True,penalty_id=award['id'])
    result=send_command(m,'add_event',{'event':scored,'related_events':[award,attempt]})
    assert result.status_code==200,result.text
    assert result.json()['projection']['event_score']['home']==1
    m=result.json()
    assert send_command(m,'remove_event',{'event_id':scored['id']}).status_code==422
    good=send_command(m,'remove_event',{'event_id':scored['id'],'related_ids':[attempt['id'],award['id']]})
    assert good.status_code==200
    assert good.json()['projection']['event_score']['home']==0


def test_failed_command_has_no_audit_or_partial_write(admin_client,match_factory,send_command):
    m=match_factory(); count=admin_client.get(f"/api/v1/matches/{m['id']}/history").json()['total']
    bad=event(player_id=str(uuid4()))
    assert send_command(m,'add_event',{'event':bad}).status_code==422
    saved=admin_client.get(f"/api/v1/matches/{m['id']}").json()
    assert saved['revision']==m['revision'] and saved['protocol']['events']==[]
    assert admin_client.get(f"/api/v1/matches/{m['id']}/history").json()['total']==count


def test_edit_penalty_outcome_atomically_removes_or_adds_goal(match_factory,send_command):
    m=match_factory(); award=event('penalty_awarded'); attempt=event('penalty_attempt',penalty_id=award['id'],outcome='goal'); goal=event(from_penalty=True,penalty_id=award['id'])
    r=send_command(m,'add_event',{'event':attempt,'related_events':[award,goal]});assert r.status_code==200
    missed=send_command(r.json(),'replace_event',{'event':{**attempt,'outcome':'saved'},'remove_related_ids':[goal['id']]})
    assert missed.status_code==200,missed.text
    assert missed.json()['projection']['event_score']['home']==0
    scored=send_command(missed.json(),'replace_event',{'event':attempt,'related_events':[goal]})
    assert scored.status_code==200,scored.text
    assert scored.json()['projection']['event_score']['home']==1
    unrelated=event('foul'); r=send_command(scored.json(),'add_event',{'event':unrelated})
    bad=send_command(r.json(),'replace_event',{'event':{**attempt,'outcome':'saved'},'remove_related_ids':[unrelated['id'],goal['id']]})
    assert bad.status_code==422
