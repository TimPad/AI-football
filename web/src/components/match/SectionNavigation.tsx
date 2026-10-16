import type {MouseEvent} from 'react';
export type SectionItem={id:string;label:string;group?:string;state?:'attention'|'done'};
const STATE_TITLE={attention:'Требует внимания',done:'Готово'} as const;

// Группы показывают порядок работы; ссылки и их имена не зависят от группы.
export function SectionNavigation({items,selected,onSelect,label='Разделы',href}:{items:SectionItem[];selected:string;
 onSelect:(id:string)=>void;label?:string;href?:(id:string)=>string}){
 const open=(e:MouseEvent,id:string)=>{if(e.metaKey||e.ctrlKey||e.shiftKey||e.button!==0)return;e.preventDefault();onSelect(id)};
 const link=(item:SectionItem)=><a key={item.id} href={href?.(item.id)??`?tab=${item.id}`} aria-current={item.id===selected?'page':undefined}
  title={item.state?STATE_TITLE[item.state]:undefined} onClick={e=>open(e,item.id)}>{item.label}{item.state&&<i className={`nav-state ${item.state}`} aria-hidden="true"/>}</a>;
 if(!items.some(i=>i.group))return <nav className="section-nav" aria-label={label}>{items.map(link)}</nav>;
 const groups:{name:string;items:SectionItem[]}[]=[];
 for(const item of items){const name=item.group??'';const last=groups[groups.length-1];if(last&&last.name===name)last.items.push(item);else groups.push({name,items:[item]})}
 return <nav className="section-nav grouped" aria-label={label}>{groups.map((g,i)=><div className="nav-group" key={`${g.name}:${i}`}>
  {g.name&&<span className="nav-group-label">{g.name}</span>}<div className="nav-group-links">{g.items.map(link)}</div></div>)}</nav>;
}
