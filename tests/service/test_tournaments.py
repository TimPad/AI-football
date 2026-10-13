def test_rule_versions_are_immutable(admin_client,tournament_factory,regulation_data):
    t=tournament_factory(); url=f"/api/v1/tournaments/{t['id']}/regulations"
    old=admin_client.post(url,json={'variant_name':'Группа','rules':regulation_data})
    assert old.status_code==201
    new=admin_client.post(url,json={'variant_name':'Группа','rules':{**regulation_data,'periods_s':[900,900]}})
    assert new.status_code==201
    assert new.json()['version']==2
    items=admin_client.get(url).json()['items']
    assert next(x for x in items if x['id']==old.json()['id'])==old.json()


def test_dates_timezone_revision(admin_client,tournament_factory):
    for changes in ({'timezone':'Not/AZone'},{'ends_on':'2026-01-01'}):
        data={'name':'Кубок','season':'2026','starts_on':'2026-10-01','ends_on':'2026-12-31',
              'timezone':'Europe/Moscow',**changes}
        assert admin_client.post('/api/v1/tournaments',json=data).status_code==422
    t=tournament_factory(); url=f"/api/v1/tournaments/{t['id']}"
    assert admin_client.patch(url,json={'expected_revision':0,'name':'Обновлён'}).status_code==200
    assert admin_client.patch(url,json={'expected_revision':0,'name':'Старый'}).status_code==409


def test_invalid_patch_and_archived_regulations(admin_client,tournament_factory,regulation_data):
    t=tournament_factory(); url=f"/api/v1/tournaments/{t['id']}"
    assert admin_client.patch(url,json={'expected_revision':0,'timezone':'Not/AZone'}).status_code==422
    assert admin_client.patch(url,json={'expected_revision':0,'archived':True}).status_code==200
    assert admin_client.post(url+'/regulations',json={'variant_name':'Группа','rules':regulation_data}).status_code==422


def test_parallel_versions_get_distinct_numbers(admin_client,tournament_factory,regulation_data):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    t=tournament_factory(); url=f"/api/v1/tournaments/{t['id']}/regulations"
    barrier=Barrier(2)
    def send(_):
        with TestClient(admin_client.app) as c:
            c.headers.update(admin_client.headers); c.cookies.update(admin_client.cookies)
            barrier.wait()
            r=c.post(url,json={'variant_name':'Группа','rules':regulation_data})
            assert r.status_code==201
            return r.json()['version']
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(send,range(2)))==[1,2]
