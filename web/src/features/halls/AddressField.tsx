import {useEffect,useId,useRef,useState,type KeyboardEvent} from 'react';
import {api} from '../../api/client';
import {Field,ErrorBox} from '../../components/ui';
import {YandexMapsLink} from '../../components/YandexMapsLink';
import './address.css';
export type AddressValue={address:string,latitude:number|null,longitude:number|null,selectionToken:string|null,source:'manual'|'yandex'};
type Suggestion={id:string,title:string,subtitle:string,address:string};
export function AddressField({value,onChange,disabled=false,onBusyChange}:{value:AddressValue,onChange:(v:AddressValue)=>void,disabled?:boolean,onBusyChange?:(v:boolean)=>void}){
 const id=useId();const [query,setQuery]=useState('');const [items,setItems]=useState<Suggestion[]>([]);const [open,setOpen]=useState(false);const [active,setActive]=useState(-1);const [loading,setLoading]=useState(false);const [resolving,setResolving]=useState(false);const [available,setAvailable]=useState(true);const [error,setError]=useState<unknown>();
 const generation=useRef(0);const resolution=useRef<AbortController|null>(null);
 useEffect(()=>{onBusyChange?.(resolving)},[resolving,onBusyChange]);
 useEffect(()=>()=>resolution.current?.abort(),[]);
 useEffect(()=>{const controller=new AbortController();if(disabled||query.trim().length<3||query.length>200){setLoading(false);setItems([]);return}
  setLoading(true);const timer=setTimeout(()=>{api<{available:boolean,items:Suggestion[]}>(`/halls/address-suggestions?q=${encodeURIComponent(query.trim())}`,{signal:controller.signal}).then(result=>{if(!controller.signal.aborted){setItems(result.items);setAvailable(result.available);setLoading(false);setOpen(true);setActive(-1)}}).catch(e=>{if(!controller.signal.aborted){setError(e);setItems([]);setLoading(false)}})},300);
  return()=>{clearTimeout(timer);controller.abort()};
 },[query,disabled]);
 function type(address:string){generation.current++;resolution.current?.abort();setResolving(false);setItems([]);setError(undefined);setQuery(address);setOpen(true);setActive(-1);onChange({address,latitude:null,longitude:null,selectionToken:null,source:'manual'})}
 async function select(item:Suggestion){const version=++generation.current;resolution.current?.abort();const controller=new AbortController();resolution.current=controller;setResolving(true);setError(undefined);setOpen(false);
  try{const result=await api<{address:string,latitude:number,longitude:number,address_selection_token:string}>('/halls/address-resolution',{method:'POST',body:JSON.stringify({suggestion_id:item.id}),signal:controller.signal});if(version!==generation.current||controller.signal.aborted)return;
   onChange({address:result.address,latitude:result.latitude,longitude:result.longitude,selectionToken:result.address_selection_token,source:'yandex'});setQuery('');setItems([]);
  }catch(e){if(!controller.signal.aborted&&version===generation.current)setError(e)}finally{if(version===generation.current)setResolving(false)}
 }
 function key(e:KeyboardEvent<HTMLInputElement>){if(e.key==='Escape'){e.preventDefault();setOpen(false)}else if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();setOpen(true);setActive(n=>Math.max(0,Math.min(items.length-1,n+(e.key==='ArrowDown'?1:-1))))}else if(e.key==='Enter'&&(resolving||loading||open&&items.length)){e.preventDefault();if(!resolving&&!loading&&items.length)void select(items[Math.max(0,active)])}}
 return <div className="address-field" onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setOpen(false)}}><Field label="Адрес зала"><input role="combobox" aria-autocomplete="list" aria-expanded={open&&items.length>0} aria-controls={`${id}-suggestions`} aria-activedescendant={open&&active>=0?`${id}-${active}`:undefined} disabled={disabled} required maxLength={1000} value={value.address} placeholder="Город, улица, дом" onChange={e=>type(e.target.value)} onKeyDown={key} autoComplete="off"/></Field>
  {open&&items.length>0&&<ul className="address-suggestions" role="listbox" id={`${id}-suggestions`} aria-label="Адреса из Яндекс Карт">{items.map((item,i)=><li key={item.id} role="option" id={`${id}-${i}`} aria-selected={i===active} onMouseDown={e=>e.preventDefault()} onClick={()=>void select(item)}><b>{item.title}</b><span>{item.subtitle||item.address}</span></li>)}</ul>}
  <div className="address-status" role="status">{resolving?'Уточняем точку на карте…':loading?'Ищем адрес…':value.latitude!=null&&value.longitude!=null?'Точка на карте сохранена':query.length>=3&&!items.length&&!error?(available?'Подсказок нет. Адрес можно оставить вручную.':'Введите адрес вручную.'):value.address?'Адрес введён вручную':''}</div>
  <ErrorBox error={error}/><YandexMapsLink address={value.address} latitude={value.latitude} longitude={value.longitude}/>
 </div>;
}
