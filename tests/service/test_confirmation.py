from .test_events import event


def finish(send,m):
    r=send(m,'set_totals',{'reported_totals':{'home':{'score':3},'away':{'score':2}}})
    assert r.status_code==200,r.text
    r=send(r.json(),'set_status',{'status':'ended'}); assert r.status_code==200
    return r.json()


def test_partial_confirmation_and_versions(admin_client,match_factory,send_command):
    m=finish(send_command,match_factory())
    assert send_command(m,'confirm',{'acknowledge_incomplete':False}).status_code==422
    confirmed=send_command(m,'confirm',{'acknowledge_incomplete':True}); assert confirmed.status_code==200
    m=confirmed.json()
    versions=admin_client.get(f"/api/v1/matches/{m['id']}/versions").json()['items']
    assert len(versions)==1
    assert send_command(m,'add_event',{'event':event()}).status_code==422
    reopened=send_command(m,'reopen',{}); assert reopened.status_code==200
    assert admin_client.get(f"/api/v1/matches/{m['id']}/versions").json()['items'][0]['snapshot']['protocol']['reported_totals']['home']['score']==3


def test_public_snapshot_does_not_change_with_draft(admin_client,match_factory,send_command,client):
    m=finish(send_command,match_factory())
    m=send_command(m,'set_notes',{'notes':'Секретная внутренняя заметка','public_notes':'Публичная заметка'}).json()
    m=send_command(m,'confirm',{'acknowledge_incomplete':True}).json()
    version=admin_client.get(f"/api/v1/matches/{m['id']}/versions").json()['items'][0]
    assert client.get('/api/v1/public/protocols/'+str(version['id'])).status_code==404
    published=send_command(m,'publish',{'version_id':version['id']}); assert published.status_code==200
    versions=admin_client.get(f"/api/v1/matches/{m['id']}/versions").json()['items']; public_id=versions[0]['public_id']
    r=client.get('/api/v1/public/protocols/'+public_id)
    assert r.status_code==200 and 'Секретная' not in r.text
    assert r.json()['protocol']['public_notes']=='Публичная заметка'
    reopened=send_command(published.json(),'reopen',{}).json()
    changed=send_command(reopened,'set_totals',{'reported_totals':{'home':{'score':9},'away':{'score':2}}})
    assert changed.status_code==200
    assert client.get('/api/v1/public/protocols/'+public_id).json()['projection']['effective_score']['home']==3
    unpublish=send_command(changed.json(),'unpublish',{}); assert unpublish.status_code==200
    assert client.get('/api/v1/public/protocols/'+public_id).status_code==404


def test_full_goal_journal_cannot_hide_wrong_score(admin_client,match_factory,send_command):
    m=match_factory()
    m=send_command(m,'add_event',{'event':event()}).json()
    m=finish(send_command,m)
    m=send_command(m,'set_completeness',{'goals':'complete'}).json()
    assert send_command(m,'confirm',{'acknowledge_incomplete':True}).status_code==422
    fixed=send_command(m,'set_totals',{'reported_totals':{'home':{'score':1},'away':{'score':0}}}).json()
    confirmed=send_command(fixed,'confirm',{'acknowledge_incomplete':True})
    assert confirmed.status_code==200


def test_duplicate_confirm_and_parallel_confirm_are_single_version(admin_client,match_factory,send_command):
    from uuid import uuid4
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    m=finish(send_command,match_factory()); barrier=Barrier(2)
    def confirm(_):
        with TestClient(admin_client.app) as c:
            c.headers.update(admin_client.headers); c.cookies.update(admin_client.cookies)
            barrier.wait()
            return c.post(f"/api/v1/matches/{m['id']}/commands",json={'request_id':str(uuid4()),
                'expected_revision':m['revision'],'kind':'confirm','payload':{'acknowledge_incomplete':True}}).status_code
    with ThreadPoolExecutor(2) as pool: assert sorted(pool.map(confirm,range(2)))==[200,409]
    assert admin_client.get(f"/api/v1/matches/{m['id']}/versions").json()['total']==1
