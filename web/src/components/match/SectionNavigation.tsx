import type {MouseEvent} from 'react';
export type SectionItem={id:string;label:string;state?:'attention'|'done';steps?:SectionItem[]};
const STATE_TITLE={attention:'Требует внимания',done:'Готово'} as const;

// Разделы — одной строкой. У раздела могут быть шаги: они видны строкой ниже, только когда раздел открыт.
// Ссылка раздела ведёт на его первый шаг (id раздела совпадает с одним из шагов).
export function SectionNavigation({items,selected,onSelect,label='Разделы',href}:{items:SectionItem[];selected:string;
 onSelect:(id:string)=>void;label?:string;href?:(id:string)=>string}){
 const open=(e:MouseEvent,id:string)=>{if(e.metaKey||e.ctrlKey||e.shiftKey||e.button!==0)return;e.preventDefault();onSelect(id)};
 const link=(item:SectionItem,current:boolean,expanded=false)=><a key={item.id} href={href?.(item.id)??`?tab=${item.id}`} aria-current={current?'page':undefined} className={expanded?'open':undefined}
  title={item.state?STATE_TITLE[item.state]:undefined} onClick={e=>open(e,item.id)}>{item.label}{item.state&&<i className={`nav-state ${item.state}`} aria-hidden="true"/>}</a>;
 const active=items.find(i=>i.id===selected||i.steps?.some(s=>s.id===selected));
 const steps=active?.steps&&active.steps.length>1?active.steps:null;
 if(!items.some(i=>i.steps))return <nav className="section-nav" aria-label={label}>{items.map(i=>link(i,i.id===selected))}</nav>;
 return <nav className="section-nav-steps" aria-label={label}>
  <div className="section-nav">{items.map(i=>link(i,i===active&&!steps,i===active&&!!steps))}</div>
  {steps&&<div className="section-steps">{steps.map(s=>link(s,s.id===selected))}</div>}
 </nav>;
}
