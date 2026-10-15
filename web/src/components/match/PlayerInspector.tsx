import './match.css';
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {X} from 'lucide-react';

const FOCUSABLE='a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
const NARROW='(max-width: 1023px)';
const narrowNow=()=>typeof window.matchMedia==='function'&&window.matchMedia(NARROW).matches;

// Панель на desktop, модальный диалог на узком экране; Escape и возврат фокуса в обоих случаях.
export function PlayerInspector({title,onClose,children}:{title:string;onClose:()=>void;children:ReactNode}){
 const panel=useRef<HTMLElement>(null);const closeRef=useRef<HTMLButtonElement>(null);
 const [modal,setModal]=useState(narrowNow);
 useEffect(()=>{
  if(typeof window.matchMedia!=='function')return;
  const query=window.matchMedia(NARROW);const update=()=>setModal(query.matches);
  query.addEventListener('change',update);return()=>query.removeEventListener('change',update);
 },[]);
 useEffect(()=>{
  const trigger=document.activeElement as HTMLElement|null;closeRef.current?.focus();
  return()=>{if(trigger?.isConnected)trigger.focus()};
 },[]);
 useEffect(()=>{
  const key=(e:KeyboardEvent)=>{
   if(e.key==='Escape'){e.preventDefault();onClose();return}
   if(e.key!=='Tab'||!modal||!panel.current)return;
   const items=[...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];if(!items.length)return;
   const first=items[0],last=items[items.length-1];
   if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
   else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
  };
  window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
 },[modal,onClose]);
 return <>{modal&&<div className="inspector-shade" onClick={onClose}/>}
  <aside ref={panel} className={`player-inspector${modal?' modal':''}`} role="dialog" aria-modal={modal||undefined} aria-label={title}>
   <div className="inspector-head"><h2>{title}</h2><button ref={closeRef} className="icon-button" onClick={onClose} aria-label="Закрыть карточку игрока"><X/></button></div>
   {children}
  </aside></>;
}
