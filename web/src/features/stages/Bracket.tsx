import {useState} from 'react';
import {Link} from 'react-router-dom';
import type {PairView,SectionView,SideView} from './api';

const dateFormat=(iso:string,timezone:string)=>new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',timeZone:timezone}).format(new Date(iso));

function Team({side,score,won}:{side:SideView;score?:string;won:boolean}){
 return <div className={`pair-team${won?' won':''}${side.team?'':' unknown'}`}><span>{side.label}</span>{score!==undefined&&<b>{score}</b>}</div>;
}

export function PairCard({pair,timezone,matchHref,action}:{pair:PairView;timezone:string;matchHref?:(id:string)=>string;action?:(pair:PairView)=>React.ReactNode}){
 const scored=pair.legs.filter(l=>l.score);
 const total=(side:'home'|'away')=>scored.length?String(scored.reduce((sum,l)=>sum+(l.score![side]??0),0)):undefined;
 const pens=pair.legs.at(-1)?.shootout;
 const next=pair.legs.find(l=>!l.score);
 const when=pair.bye?'Проходит без матча':next?(next.scheduled_at?dateFormat(next.scheduled_at,timezone):'Дата не назначена'):null;
 const link=pair.legs.find(l=>l.match_id)?.match_id;
 return <article className="pair-card" aria-label={`${pair.label}: ${pair.home.label} — ${pair.away.label}`}>
  <Team side={pair.home} score={total('home')} won={pair.winner==='home'}/>
  {!pair.bye&&<Team side={pair.away} score={total('away')} won={pair.winner==='away'}/>}
  <div className="pair-meta">{pens&&pens.home!=null&&<span>Пенальти {pens.home}:{pens.away}</span>}{when&&<span>{when}</span>}
   {pair.note&&<span className="warning">{pair.note}</span>}{link&&matchHref&&<Link to={matchHref(link)}>Матч</Link>}{action?.(pair)}</div>
 </article>;
}

// Сетка: на телефоне вкладки раундов, на широком экране — колонки раундов с прокруткой внутри блока.
export function Bracket({sections,timezone,matchHref,action}:{sections:SectionView[];timezone:string;matchHref?:(id:string)=>string;action?:(pair:PairView)=>React.ReactNode}){
 const [sectionKey,setSection]=useState(sections[0]?.key);
 const section=sections.find(s=>s.key===sectionKey)??sections[0];
 const [roundIndex,setRound]=useState(0);
 if(!section)return null;
 const round=Math.min(roundIndex,section.rounds.length-1);
 return <section className="bracket">
  {sections.length>1&&<div className="segmented" role="group" aria-label="Часть сетки">{sections.map(s=><button key={s.key} type="button" className={s.key===section.key?"active":""} aria-pressed={s.key===section.key} onClick={()=>{setSection(s.key);setRound(0)}}>{s.name}</button>)}</div>}
  <div role="tablist" aria-label="Раунды" className="round-tabs">{section.rounds.map((r,i)=><button key={r.round_no+r.name} role="tab" type="button" aria-selected={i===round} onClick={()=>setRound(i)}>{r.name}</button>)}</div>
  <div className="bracket-rounds" data-round={round}>{section.rounds.map((r,i)=><div key={r.round_no+r.name} className="bracket-round" role="tabpanel" aria-label={r.name} data-active={i===round||undefined}>
   <h4>{r.name}</h4>{r.pairs.map(p=><PairCard key={p.key} pair={p} timezone={timezone} matchHref={matchHref} action={action}/>)}</div>)}</div>
 </section>;
}
