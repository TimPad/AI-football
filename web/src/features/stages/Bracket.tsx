import {useEffect,useRef,useState,type KeyboardEvent} from 'react';
import type {PairView,SectionView} from './api';
import {PairCard} from './PairCard';
import {BracketTree} from './BracketTree';
export {PairCard} from './PairCard';

function useWide(){
 const query=typeof window!=='undefined'&&window.matchMedia?window.matchMedia('(min-width: 900px)'):null;
 const [wide,setWide]=useState(Boolean(query?.matches));
 useEffect(()=>{if(!query)return;const on=()=>setWide(query.matches);query.addEventListener?.('change',on);return()=>query.removeEventListener?.('change',on)},[query]);
 return wide;
}
const reduced=()=>typeof window!=='undefined'&&Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

// Телефон: ряд раундов и пролистывание вбок с привязкой; открыт текущий раунд.
function Rounds({section,timezone,matchHref,action,path,onTeam}:{section:SectionView;timezone:string;matchHref?:(id:string)=>string;action?:(p:PairView)=>React.ReactNode;path:string|null;onTeam:(id:string)=>void}){
 const start=Math.max(0,section.rounds.findIndex(r=>r.round_no===section.current_round));
 const [index,setIndex]=useState(start);const strip=useRef<HTMLDivElement>(null);const tabs=useRef<(HTMLButtonElement|null)[]>([]);
 const show=(i:number,focus=false)=>{setIndex(i);const el=strip.current;if(el?.scrollTo)el.scrollTo({left:i*el.clientWidth,behavior:reduced()?'auto':'smooth'});if(focus)tabs.current[i]?.focus()};
 useEffect(()=>{const el=strip.current;if(el?.scrollTo)el.scrollTo({left:start*el.clientWidth})},[start]);
 const onScroll=()=>{const el=strip.current;if(!el||!el.clientWidth)return;const i=Math.round(el.scrollLeft/el.clientWidth);if(i!==index)setIndex(i)};
 const onKey=(e:KeyboardEvent)=>{if(e.key==='ArrowRight')show(Math.min(index+1,section.rounds.length-1),true);if(e.key==='ArrowLeft')show(Math.max(index-1,0),true)};
 return <>
  <div role="tablist" aria-label="Раунды" className="round-tabs" onKeyDown={onKey}>{section.rounds.map((r,i)=><button key={r.round_no+r.name} ref={el=>{tabs.current[i]=el}} role="tab" type="button" id={`tab-${section.key}-${i}`}
   aria-selected={i===index} tabIndex={i===index?0:-1} aria-controls={`round-${section.key}-${i}`} onClick={()=>show(i)}>{r.name}</button>)}</div>
  <div className="bracket-strip" ref={strip} onScroll={onScroll}>{section.rounds.map((r,i)=><div key={r.round_no+r.name} id={`round-${section.key}-${i}`} className="bracket-round" role="tabpanel"
   aria-labelledby={`tab-${section.key}-${i}`} data-active={i===index||undefined}>
   {r.pairs.map(p=><PairCard key={p.key} pair={p} timezone={timezone} matchHref={matchHref} action={action} path={path} onTeam={onTeam}/>)}</div>)}</div>
 </>;
}

export function Bracket({sections,timezone,matchHref,action,wide:forced}:{sections:SectionView[];timezone:string;matchHref?:(id:string)=>string;action?:(pair:PairView)=>React.ReactNode;wide?:boolean}){
 const media=useWide();const wide=forced??media;
 const [sectionKey,setSection]=useState(sections[0]?.key);const [path,setPath]=useState<string|null>(null);
 const section=sections.find(s=>s.key===sectionKey)??sections[0];
 const onTeam=(id:string)=>setPath(old=>old===id?null:id);
 useEffect(()=>{if(!path)return;const off=(e:globalThis.KeyboardEvent)=>{if(e.key==='Escape')setPath(null)};document.addEventListener('keydown',off);return()=>document.removeEventListener('keydown',off)},[path]);
 if(!section)return null;
 return <section className="bracket" aria-label="Сетка">
  {sections.length>1&&<div className="segmented" role="group" aria-label="Часть сетки">{sections.map(s=><button key={s.key} type="button" className={s.key===section.key?'active':''} aria-pressed={s.key===section.key} onClick={()=>setSection(s.key)}>{s.name}</button>)}</div>}
  {path&&<p className="muted small" role="status">Показан путь команды. Нажмите на неё ещё раз или Esc, чтобы снять.</p>}
  {wide?<BracketTree key={section.key} section={section} timezone={timezone} matchHref={matchHref} action={action} path={path} onTeam={onTeam}/>
   :<Rounds key={section.key} section={section} timezone={timezone} matchHref={matchHref} action={action} path={path} onTeam={onTeam}/>}
 </section>;
}
