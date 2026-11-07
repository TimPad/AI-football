import {useRef,useState,type ReactNode} from 'react';
import {MoreHorizontal} from 'lucide-react';
import {Modal} from './ui';

export type MenuItem={label:string;onSelect:()=>void;danger?:boolean;disabled?:boolean};

// Редкие и опасные действия — в меню «…», а не рядом с обычными кнопками. Опасные подписаны красным.
export function MoreMenu({label='Ещё действия',items}:{label?:string;items:MenuItem[]}){
 const menu=useRef<HTMLDetailsElement>(null);
 return <details className="more-menu" ref={menu}><summary className="icon-button" aria-label={label} title={label}><MoreHorizontal aria-hidden="true"/></summary>
  <div className="more-menu-list" role="menu">{items.map(item=><button type="button" role="menuitem" key={item.label} className={item.danger?'danger-text':undefined} disabled={item.disabled}
   onClick={()=>{menu.current?.removeAttribute('open');item.onSelect()}}>{item.label}</button>)}</div></details>;
}

// Подтверждение опасного действия: что произойдёт и кнопка с тем же глаголом, красная.
export function ConfirmDialog({title,children,confirm,onConfirm,onClose,busy=false}:{title:string;children:ReactNode;confirm:string;onConfirm:()=>void|Promise<unknown>;onClose:()=>void;busy?:boolean}){
 const [running,setRunning]=useState(false);
 return <Modal title={title} sheet onClose={onClose}><div className="confirm-body">{children}</div>
  <div className="confirm-actions"><button type="button" onClick={onClose}>Отмена</button>
   <button type="button" className="danger" disabled={busy||running} onClick={async()=>{setRunning(true);try{await onConfirm()}finally{setRunning(false)}}}>{confirm}</button></div></Modal>;
}
