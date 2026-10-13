import {useEffect,useState,type ReactNode} from 'react';
import {errorText} from '../api/client';
export function ErrorBox({error}:{error:unknown}){return error?<div className="error" role="alert">{errorText(error)}</div>:null}
export function Field({label,children}:{label:string,children:ReactNode}){return <label className="field"><span>{label}</span>{children}</label>}
export function Check({label,checked,onChange}:{label:string,checked:boolean,onChange:(v:boolean)=>void}){return <label className="check"><input type="checkbox" checked={checked} onChange={e=>onChange(e.target.checked)}/>{label}</label>}
export function useLoad<T>(load:()=>Promise<T>,key:string){
 const [data,setData]=useState<T>();const [error,setError]=useState<unknown>();const [tick,setTick]=useState(0);
 useEffect(()=>{let active=true;setError(undefined);load().then(v=>{if(active)setData(v)}).catch(e=>{if(active)setError(e)});return()=>{active=false}},[key,tick]);
 return {data,setData,error,reload:()=>setTick(v=>v+1)};
}
export function Loading({error,retry}:{error:unknown,retry?:()=>void}){return error?<><ErrorBox error={error}/>{retry&&<button onClick={retry}>Повторить</button>}</>:<p className="muted" role="status">Загружаем…</p>}
export function Empty({children}:{children:ReactNode}){return <div className="empty">{children}</div>}
export function Modal({title,children,onClose}:{title:string,children:ReactNode,onClose:()=>void}){
 useEffect(()=>{const handler=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler)},[onClose]);
 return <div className="overlay"><section className="modal" role="dialog" aria-modal="true" aria-label={title}><div className="row"><h2>{title}</h2><button onClick={onClose} aria-label="Закрыть">×</button></div>{children}</section></div>
}
export function downloadJson(value:unknown,name='правки.json'){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url)}
