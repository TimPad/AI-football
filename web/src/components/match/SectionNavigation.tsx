import type {MouseEvent} from 'react';
export type SectionItem={id:string;label:string};

export function SectionNavigation({items,selected,onSelect,label='Разделы',href}:{items:SectionItem[];selected:string;
 onSelect:(id:string)=>void;label?:string;href?:(id:string)=>string}){
 const open=(e:MouseEvent,id:string)=>{if(e.metaKey||e.ctrlKey||e.shiftKey||e.button!==0)return;e.preventDefault();onSelect(id)};
 return <nav className="section-nav" aria-label={label}>{items.map(item=>
  <a key={item.id} href={href?.(item.id)??`?tab=${item.id}`} aria-current={item.id===selected?'page':undefined}
   onClick={e=>open(e,item.id)}>{item.label}</a>)}</nav>;
}
