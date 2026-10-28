import {useLayoutEffect,useRef,useState} from 'react';
import type {PairView,SectionView} from './api';
import {PairCard} from './PairCard';

type Line={from:string;to:string;d:string};

// Строки сетки: у раунда из k пар каждая пара занимает total/k строк, поэтому пара следующего раунда стоит по центру между своими.
export function rowsFor(section:SectionView){
 const main=section.rounds.map(r=>r.pairs.filter(p=>p.bracket!=='third'));
 const most=Math.max(1,...main.map(p=>p.length));const total=most*2;
 return {total,place:(roundIndex:number,i:number)=>{const count=main[roundIndex].length||1;const span=Math.max(1,Math.floor(total/count));return {start:i*span+2,span}}};
}

// Компьютер: дерево раундов, линии — SVG поверх по связям «победитель пары».
export function BracketTree({section,timezone,matchHref,action,path,onTeam}:{section:SectionView;timezone:string;matchHref?:(id:string)=>string;action?:(p:PairView)=>React.ReactNode;path:string|null;onTeam:(id:string)=>void}){
 const box=useRef<HTMLDivElement>(null);const [lines,setLines]=useState<Line[]>([]);const [size,setSize]=useState({w:0,h:0});
 const {total,place}=rowsFor(section);
 const third=section.rounds.flatMap(r=>r.pairs.filter(p=>p.bracket==='third'));
 const all=section.rounds.flatMap(r=>r.pairs);const byKey=Object.fromEntries(all.map(p=>[p.key,p]));
 useLayoutEffect(()=>{
  const measure=()=>{const root=box.current;if(!root)return;const base=root.getBoundingClientRect();const found:Line[]=[];
   const card=(key:string)=>root.querySelector<HTMLElement>(`[data-key="${CSS.escape(key)}"]`)?.getBoundingClientRect();
   for(const p of all)for(const from of [p.home_from,p.away_from]){
    if(!from||!byKey[from]||byKey[from].bracket==='third'||p.bracket==='third')continue;
    const a=card(from),b=card(p.key);if(!a||!b)continue;
    const x1=a.right-base.left+root.scrollLeft,y1=a.top+a.height/2-base.top,x2=b.left-base.left+root.scrollLeft,y2=b.top+b.height/2-base.top,xm=(x1+x2)/2;
    found.push({from,to:p.key,d:`M${x1} ${y1}H${xm}V${y2}H${x2}`});
   }
   setLines(found);setSize({w:root.scrollWidth,h:root.scrollHeight});};
  measure();
  const observer=typeof ResizeObserver!=='undefined'?new ResizeObserver(measure):null;if(observer&&box.current)observer.observe(box.current);
  void document.fonts?.ready.then(measure);
  return()=>observer?.disconnect();
 },[section]);
 const onPath=(key:string)=>Boolean(path&&[byKey[key]?.home.team?.entry_id,byKey[key]?.away.team?.entry_id].includes(path));
 return <div className="bracket-tree" ref={box} style={{gridTemplateColumns:`repeat(${section.rounds.length},minmax(220px,1fr))`,gridTemplateRows:`auto repeat(${total},minmax(40px,auto))`}}>
  <svg className="bracket-lines" aria-hidden="true" width={size.w} height={size.h}>{lines.map(l=><path key={l.from+l.to} d={l.d} data-path={onPath(l.from)&&onPath(l.to)||undefined}/>)}</svg>
  {section.rounds.map((r,ri)=>[<h4 key={'h'+r.round_no+r.name} style={{gridColumn:ri+1,gridRow:1}}>{r.name}</h4>,
   ...r.pairs.filter(p=>p.bracket!=='third').sort((a,b)=>a.slot-b.slot).map((p,i)=>{const {start,span}=place(ri,i);
    return <div key={p.key} className="tree-cell" style={{gridColumn:ri+1,gridRow:`${start} / span ${span}`}}><PairCard pair={p} timezone={timezone} matchHref={matchHref} action={action} path={path} onTeam={onTeam}/></div>})])}
  {third.length>0&&<div className="tree-third" style={{gridColumn:section.rounds.length,gridRow:`${total+2}`}}><h4>Матч за 3-е место</h4>{third.map(p=><PairCard key={p.key} pair={p} timezone={timezone} matchHref={matchHref} action={action} path={path} onTeam={onTeam}/>)}</div>}
 </div>;
}
