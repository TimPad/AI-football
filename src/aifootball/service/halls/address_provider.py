"""Yandex adapter and actor-bound selections. No persistent suggestion cache."""
import base64
import hashlib
import hmac
import json
import time
import logging
import re
from urllib.parse import urlparse
from aifootball.service.errors import DomainError

class RedactAddressKey(logging.Filter):
    def filter(self,record):
        # httpx INFO normally logs the full request URL, including query keys.
        def redact(value):
            text=str(value)
            return re.sub(r'([?&]apikey=)[^&\s]+',r'\1[redacted]',text) if 'apikey=' in text else value
        if isinstance(record.args,tuple):record.args=tuple(redact(value) for value in record.args)
        record.msg=redact(record.msg)
        return True
logging.getLogger('httpx').addFilter(RedactAddressKey())

def timestamp():return int(time.time())

def seal(secret,purpose,actor,payload,ttl):
    if len(secret)<32:raise DomainError('address_unavailable','Подсказки пока недоступны. Адрес можно ввести вручную.',status=503)
    body=base64.urlsafe_b64encode(json.dumps({'purpose':purpose,'actor':str(actor),'expires':timestamp()+ttl,**payload},ensure_ascii=False,separators=(',',':')).encode()).decode().rstrip('=')
    return body+'.'+hmac.new(secret.encode(),body.encode(),hashlib.sha256).hexdigest()

def unseal(secret,purpose,actor,token):
    try:
        if len(secret)<32 or len(token)>12000:raise ValueError()
        body,signature=token.rsplit('.',1)
        if not hmac.compare_digest(signature,hmac.new(secret.encode(),body.encode(),hashlib.sha256).hexdigest()):raise ValueError()
        value=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        if value['purpose']!=purpose or value['actor']!=str(actor) or value['expires']<=timestamp():raise ValueError()
        return value
    except (ValueError,TypeError,KeyError):raise DomainError('address_selection','Подсказка устарела или изменена. Выберите адрес ещё раз либо введите его вручную.',status=422)

def valid_uri(uri):
    parsed=urlparse(uri)
    return len(uri)<=4000 and parsed.scheme=='ymapsbm1' and parsed.netloc in {'geo','org'} and bool(parsed.query)

def validate_selection(settings,actor,data):
    value=unseal(settings.address_signing_secret,'selection',actor,data.address_selection_token)
    if any(value.get(key)!=getattr(data,key) for key in ['address','latitude','longitude']):
        raise DomainError('address_selection','Адрес и точка изменены. Выберите подсказку заново.',status=422)

class YandexAddressProvider:
    def __init__(self,settings):self.settings=settings
    def _get(self,url,params):
        import httpx
        try:
            with httpx.Client(timeout=2,follow_redirects=False) as client:
                response=client.get(url,params=params)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError,ValueError):
            raise DomainError('address_unavailable','Карты временно недоступны. Продолжите ввод адреса вручную.',status=503)
    def suggest(self,query):
        data=self._get('https://suggest-maps.yandex.ru/v1/suggest',{'apikey':self.settings.yandex_suggest_key,'text':query,'lang':'ru','results':7,'attrs':'uri','print_address':1,'highlight':0})
        return [{'uri':r['uri'],'title':r.get('title',{}).get('text',''),'subtitle':r.get('subtitle',{}).get('text',''),'address':r.get('address',{}).get('formatted_address','')} for r in data.get('results',[]) if valid_uri(r.get('uri',''))][:7]
    def resolve(self,uri):
        if not valid_uri(uri):raise DomainError('address_selection','Выберите адрес из списка подсказок.',status=422)
        data=self._get('https://geocode-maps.yandex.ru/v1/',{'apikey':self.settings.yandex_geocoder_key,'uri':uri,'format':'json','lang':'ru_RU','results':1})
        try:
            geo=data['response']['GeoObjectCollection']['featureMember'][0]['GeoObject']
            # Provider Point.pos is longitude, latitude. Our fields are explicit.
            longitude,latitude=map(float,geo['Point']['pos'].split())
            meta=geo['metaDataProperty']['GeocoderMetaData']
            return {'address':meta.get('Address',{}).get('formatted') or meta['text'],'latitude':latitude,'longitude':longitude}
        except (ValueError,KeyError,IndexError,TypeError):raise DomainError('address_unavailable','Не удалось уточнить точку. Выберите другой адрес или введите вручную.',status=503)

def provider(request):
    if hasattr(request.app.state,'address_provider'):return request.app.state.address_provider
    settings=request.app.state.settings
    if not(settings.yandex_address_enabled and settings.yandex_suggest_key and settings.yandex_geocoder_key and len(settings.address_signing_secret)>=32):return None
    return YandexAddressProvider(settings)
