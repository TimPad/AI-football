import {useEffect,useState,useRef,cloneElement,isValidElement,type ReactElement,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {errorText} from '../api/client';
export function ErrorBox({error}:{error:unknown}){return error?<div className="error" role="alert">{errorText(error)}</div>:null}
export function Field({label,children}:{label:string,children:ReactNode}){return <label className="field"><span>{label}</span>{isValidElement(children)?cloneElement(children as ReactElement<{'aria-label'?:string}>,{'aria-label':label}):children}</label>}
export function Check({label,checked,onChange,disabled=false}:{label:string,checked:boolean,onChange:(v:boolean)=>void,disabled?:boolean}){return <label className="check"><input disabled={disabled} type="checkbox" checked={checked} onChange={e=>onChange(e.target.checked)}/>{label}</label>}
export function useLoad<T>(load:()=>Promise<T>,key:string){
 const [data,setData]=useState<T>();const [error,setError]=useState<unknown>();const [tick,setTick]=useState(0);
 useEffect(()=>{let active=true;setError(undefined);load().then(v=>{if(active)setData(v)}).catch(e=>{if(active)setError(e)});return()=>{active=false}},[key,tick]);
 return {data,setData,error,reload:()=>setTick(v=>v+1)};
}
export function Loading({error,retry}:{error:unknown,retry?:()=>void}){return error?<><ErrorBox error={error}/>{retry&&<button onClick={retry}>Повторить</button>}</>:<p className="muted" role="status">Загружаем…</p>}
export function Empty({children}:{children:ReactNode}){return <div className="empty">{children}</div>}
// sheet — на телефоне окно выезжает снизу (нижняя панель), на широком экране обычное.
export function Modal({title,children,onClose,sheet=false}:{title:string,children:ReactNode,onClose:()=>void,sheet?:boolean}){
 const container=useRef<HTMLElement>(null);const close=useRef(onClose);close.current=onClose;
 useEffect(()=>{const opener=document.activeElement as HTMLElement|null;const focusable=()=>Array.from(container.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')??[]).filter(el=>!el.closest('[hidden]'));
  focusable()[0]?.focus();const handler=(e:KeyboardEvent)=>{if(document.querySelectorAll('[role=dialog][aria-modal=true]').item(document.querySelectorAll('[role=dialog][aria-modal=true]').length-1)!==container.current)return;if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close.current()}if(e.key==='Tab'){const items=focusable(),first=items[0],last=items.at(-1);if(!first){e.preventDefault();container.current?.focus()}else if(e.shiftKey&&(document.activeElement===first||!container.current?.contains(document.activeElement))){e.preventDefault();last?.focus()}else if(!e.shiftKey&&(document.activeElement===last||!container.current?.contains(document.activeElement))){e.preventDefault();first.focus()}}};
  document.addEventListener('keydown',handler);return()=>{document.removeEventListener('keydown',handler);if(opener?.isConnected)opener.focus()};},[]);
 return createPortal(<div className="overlay"><section onSubmit={e=>e.stopPropagation()} ref={container} tabIndex={-1} className={sheet?"modal sheet":"modal"} role="dialog" aria-modal="true" aria-label={title}><div className="row"><h2>{title}</h2><button type="button" onClick={onClose} aria-label="Закрыть">×</button></div>{children}</section></div>,document.body)
}
export function downloadJson(value:unknown,name='правки.json'){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url)}
