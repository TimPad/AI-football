from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from .test_halls import hall_body

class FakeProvider:
    def suggest(self,query):return [{'uri':'ymapsbm1://geo?data=synthetic','title':'Арена','subtitle':'Тестовый город','address':'Тестовый город, Спортивная, 1'}]
    def resolve(self,uri):
        assert uri=='ymapsbm1://geo?data=synthetic'
        return {'address':'Тестовый город, Спортивная, 1','latitude':57.62,'longitude':39.88}

@pytest.fixture
def provider(admin_client):
    admin_client.app.state.settings.address_signing_secret='test-only-address-signing-secret-123456'
    admin_client.app.state.address_provider=FakeProvider()
    return admin_client

def selection(client):
    result=client.get('/api/v1/halls/address-suggestions',params={'q':'Спортивная'})
    assert result.status_code==200,result.text
    response=client.post('/api/v1/halls/address-resolution',json={'suggestion_id':result.json()['items'][0]['id']})
    assert response.status_code==200,response.text
    return response.json()

def test_selected_address_persists_and_unchanged_address_keeps_point(provider):
    location=selection(provider);body={**hall_body(),**location,'request_id':str(uuid4())}
    response=provider.post('/api/v1/halls',json=body);assert response.status_code==201,response.text
    hall=response.json();assert (hall['latitude'],hall['longitude'],hall['address_source'])==(57.62,39.88,'yandex')
    assert 'address_selection_token' not in hall
    same={**hall_body(), 'name':'Другая вывеска','address':hall['address'],'expected_revision':hall['revision'],'request_id':str(uuid4())}
    same.pop('latitude');same.pop('longitude')
    updated=provider.put('/api/v1/halls/'+hall['id'],json=same).json()
    assert updated['latitude']==57.62 and updated['address_source']=='yandex'
    changed=provider.put('/api/v1/halls/'+hall['id'],json={**same,'expected_revision':updated['revision'],'request_id':str(uuid4()),'address':'Другой адрес'}).json()
    assert changed['latitude'] is None and changed['longitude'] is None and changed['address_source']=='manual'

def test_tokens_are_actor_bound_tamper_checked_and_replay_survives_expiry(provider,monkeypatch):
    from aifootball.service.halls import address_provider as address
    location=selection(provider);body={**hall_body(),**location,'request_id':str(uuid4())}
    bad=provider.post('/api/v1/halls',json={**body,'latitude':39.88,'longitude':57.62});assert bad.status_code==422
    assert provider.post('/api/v1/halls',json={**body,'address':'Подмена'}).status_code==422
    first=provider.post('/api/v1/halls',json=body);assert first.status_code==201,first.text
    monkeypatch.setattr(address,'timestamp',lambda:10**12)
    assert provider.post('/api/v1/halls',json=body).json()==first.json()
    assert provider.post('/api/v1/halls',json={**body,'request_id':str(uuid4())}).status_code==422
    assert provider.post('/api/v1/halls/address-resolution',json={'suggestion_id':'https://example.com'}).status_code==422

def test_manual_fallback_and_provider_failures(admin_client,provider):
    provider.app.state.address_provider=None
    data=provider.get('/api/v1/halls/address-suggestions?q=Город').json()
    assert data['available'] is False and data['items']==[]
    assert provider.post('/api/v1/halls',json=hall_body()).status_code==201
    class Broken(FakeProvider):
        def suggest(self,query):raise TimeoutError()
    provider.app.state.address_provider=Broken()
    response=provider.get('/api/v1/halls/address-suggestions?q=Город')
    assert response.status_code==503 and 'manual' not in response.text
    with TestClient(provider.app) as guest:assert guest.get('/api/v1/halls/address-suggestions?q=Город').status_code==401

def test_foreign_selection_and_actor_rate_limit(provider):
    from sqlalchemy.orm import Session
    from aifootball.service.auth.cli import create_admin
    location=selection(provider)
    with Session(provider.app.state.engine) as db:
        create_admin(db,'second','another-testing-password');db.commit()
    with TestClient(provider.app) as other:
        other.headers['Origin']=provider.app.state.settings.allowed_origin
        auth=other.post('/api/v1/auth/login',json={'login':'second','password':'another-testing-password'}).json()
        other.headers['X-CSRF-Token']=auth['csrf_token']
        assert other.post('/api/v1/halls',json={**hall_body(),**location}).status_code==422
    for _ in range(28):assert provider.get('/api/v1/halls/address-suggestions?q=Город').status_code==200
    assert provider.get('/api/v1/halls/address-suggestions?q=Город').status_code==429

def test_adapter_converts_provider_order_and_redacts_keys(provider,monkeypatch,caplog):
    import httpx,logging
    from aifootball.service.halls.address_provider import YandexAddressProvider
    provider.app.state.settings.yandex_geocoder_key='fake-secret-not-for-logs'
    original=httpx.Client
    def handle(request):
        assert request.url.host=='geocode-maps.yandex.ru'
        assert request.url.params['uri']=='ymapsbm1://geo?data=synthetic'
        return httpx.Response(200,json={'response':{'GeoObjectCollection':{'featureMember':[{'GeoObject':{'Point':{'pos':'39.88 57.62'},'metaDataProperty':{'GeocoderMetaData':{'text':'Город, 1'}}}}]}}})
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(handle)))
    caplog.set_level(logging.INFO,logger='httpx')
    result=YandexAddressProvider(provider.app.state.settings).resolve('ymapsbm1://geo?data=synthetic')
    assert (result['latitude'],result['longitude'])==(57.62,39.88)
    assert 'fake-secret-not-for-logs' not in caplog.text
