import type {PairView,RoundView} from './api';
import {PairCard} from './PairCard';

// Матчи группы по турам: даты и счёт сыгранных; большие группы свёрнуты.
export function GroupMatches({rounds,group,timezone,matchHref}:{rounds:RoundView[];group:number|null;timezone:string;matchHref?:(id:string)=>string}){
 const tours=rounds.map(r=>({...r,pairs:r.pairs.filter((p:PairView)=>!p.bye&&(group===null||p.group_no===group))})).filter(r=>r.pairs.length);
 const count=tours.reduce((n,r)=>n+r.pairs.length,0);
 if(!count)return null;
 return <details className="group-matches" open={count<=6}><summary>Матчи{group===null?'':' группы'} · {count}</summary>
  {tours.map(r=><div key={r.round_no} className="tour"><h4>{r.name}</h4>{r.pairs.map(p=><PairCard key={p.key} pair={p} timezone={timezone} matchHref={matchHref}/>)}</div>)}</details>;
}
