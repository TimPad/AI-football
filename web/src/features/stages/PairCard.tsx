import {Check} from 'lucide-react';
import {Link} from 'react-router-dom';
import type {PairView,SideView} from './api';
import {legStatus,pairSpeech,pairTotals,shortDate} from './labels';

// Две буквы названия — вместо пустого места, когда эмблемы нет.
const initials=(name:string)=>name.split(/\s+/).filter(w=>/^[\p{L}\d]/u.test(w)).slice(0,2).map(w=>w[0]).join('').toUpperCase();

function Team({side,score,won,path,onTeam}:{side:SideView;score?:string;won:boolean;path?:string|null;onTeam?:(id:string)=>void}){
 const id=side.team?.entry_id;
 const name=onTeam&&id?<button type="button" className="team-path" aria-pressed={path===id} onClick={()=>onTeam(id)}>{side.label}</button>:<span>{side.label}</span>;
 return <div className={`pair-team${won?' won':''}${side.team?'':' unknown'}`}>
  {side.team?.logo_id?<img className="team-logo" src={`/api/v1/public/catalog/team-logos/${side.team.logo_id}`} alt="" width={20} height={20}/>
   :<span className="team-logo initials" aria-hidden="true">{side.team?initials(side.team.name):''}</span>}
  {name}{won&&<Check className="won-mark" aria-hidden="true"/>}{score!==undefined&&<b>{score}</b>}</div>;
}

// Карточка пары: итог, у каждого матча своя строка с датой и счётом; строка матча — ссылка на матч.
export function PairCard({pair,timezone,matchHref,action,path,onTeam}:{pair:PairView;timezone:string;matchHref?:(id:string)=>string;action?:(pair:PairView)=>React.ReactNode;path?:string|null;onTeam?:(id:string)=>void}){
 const totals=pairTotals(pair);const pens=pair.legs.at(-1)?.shootout;
 const level=totals&&totals.home===totals.away&&pens&&pens.home!=null;
 const score=(side:'home'|'away')=>totals?`${totals[side]}${level?` (${pens![side]})`:''}`:undefined;
 const onPath=Boolean(path&&[pair.home.team?.entry_id,pair.away.team?.entry_id].includes(path));
 return <article className="pair-card" data-key={pair.key} data-path={onPath||undefined} aria-label={pairSpeech(pair,timezone)}>
  <Team side={pair.home} score={score('home')} won={pair.winner==='home'} path={path} onTeam={onTeam}/>
  {!pair.bye&&<Team side={pair.away} score={score('away')} won={pair.winner==='away'} path={path} onTeam={onTeam}/>}
  <ul className="pair-legs">{pair.bye?<li className="pair-leg">Проходит без матча</li>:pair.legs.map(leg=>{
   const status=legStatus(leg);const when=leg.scheduled_at?shortDate(leg.scheduled_at,timezone):leg.technical||leg.annulled?'':'Дата не назначена';
   const text=<>{pair.legs.length>1&&<span>Матч {leg.leg}</span>}{when&&<span>{when}</span>}{status&&<span className={leg.status==='live'?'live':undefined}>{status}</span>}
    {leg.score&&!leg.annulled&&<b>{leg.score.home} : {leg.score.away}</b>}</>;
   return <li key={leg.leg}>{leg.match_id&&matchHref?<Link className="pair-leg" to={matchHref(leg.match_id)}>{text}</Link>:<div className="pair-leg">{text}</div>}</li>})}</ul>
  {(pair.note||action)&&<div className="pair-meta">{pair.note&&<span className="warning">{pair.note}</span>}{action?.(pair)}</div>}
 </article>;
}
