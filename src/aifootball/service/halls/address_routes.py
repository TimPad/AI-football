from uuid import UUID
from fastapi import APIRouter,Depends,Query,Request,Response
from pydantic import BaseModel,Field,ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from aifootball.service.auth.security import require_admin,require_csrf
from aifootball.service.db import get_session
from aifootball.service.errors import DomainError
from aifootball.service.halls import address_provider as addresses
from aifootball.service.halls.models import HallAddressLimit
from aifootball.service.tournaments.schemas import Input

router=APIRouter()
class AddressSuggestion(BaseModel):
    id:str
    title:str
    subtitle:str
    address:str
class AddressSuggestions(BaseModel):
    available:bool
    items:list[AddressSuggestion]
class AddressResolution(Input):
    suggestion_id:str=Field(min_length=1,max_length=12000)
class ResolvedAddress(BaseModel):
    address:str=Field(min_length=1,max_length=1000)
    latitude:float=Field(ge=-90,le=90,allow_inf_nan=False)
    longitude:float=Field(ge=-180,le=180,allow_inf_nan=False)
class AddressSelection(ResolvedAddress):
    address_selection_token:str

def throttle(db,actor):
    from aifootball.service.halls.operations import lock_request
    with db.begin():
        lock_request(db,actor)
        row=db.get(HallAddressLimit,actor);window=addresses.timestamp()//60
        if not row:row=HallAddressLimit(actor_id=actor,window=window,count=0);db.add(row)
        if row.window!=window:row.window=window;row.count=0
        if row.count>=30:raise DomainError('address_rate_limit','Слишком много запросов. Подождите минуту или введите адрес вручную.',status=429)
        row.count+=1

@router.get('/halls/address-suggestions',response_model=AddressSuggestions)
def suggest(request:Request,response:Response,q:str=Query(min_length=3,max_length=200),actor=Depends(require_admin),db:Session=Depends(get_session)):
    response.headers['Cache-Control']='no-store';adapter=addresses.provider(request)
    if adapter is None:return {'available':False,'items':[]}
    throttle(db,actor.id)
    try:items=adapter.suggest(q)
    except (TimeoutError,ConnectionError):raise DomainError('address_unavailable','Подсказки временно недоступны. Адрес можно ввести вручную.',status=503)
    secret=request.app.state.settings.address_signing_secret
    return {'available':True,'items':[{'id':addresses.seal(secret,'suggestion',actor.id,{'uri':r['uri']},900),**{k:r.get(k,'') for k in ['title','subtitle','address']}} for r in items[:7] if addresses.valid_uri(r.get('uri',''))]}

@router.post('/halls/address-resolution',response_model=AddressSelection)
def resolve(data:AddressResolution,request:Request,response:Response,actor=Depends(require_csrf),db:Session=Depends(get_session)):
    response.headers['Cache-Control']='no-store';secret=request.app.state.settings.address_signing_secret
    token=addresses.unseal(secret,'suggestion',actor.id,data.suggestion_id)
    if not addresses.valid_uri(token.get('uri','')):raise DomainError('address_selection','Выберите адрес из списка.',status=422)
    adapter=addresses.provider(request)
    if adapter is None:raise DomainError('address_unavailable','Подсказки недоступны. Введите адрес вручную.',status=503)
    throttle(db,actor.id)
    try:resolved=ResolvedAddress.model_validate(adapter.resolve(token['uri'])).model_dump()
    except (TimeoutError,ConnectionError,ValidationError):raise DomainError('address_unavailable','Точку не удалось уточнить. Введите адрес вручную.',status=503)
    return {**resolved,'address_selection_token':addresses.seal(secret,'selection',actor.id,resolved,24*3600)}
