import {useState} from 'react';
import {Link} from 'react-router-dom';
import type {GroupView} from './api';
import {criteriaText} from './labels';

// Таблица группы: на телефоне «№, команда, игры, очки», касание строки раскрывает подробности.
export function GroupTable({group,criteria,teamHref,advanceNote,withdrawn}:{group:GroupView;criteria:string[];teamHref?:(teamId:string)=>string;advanceNote?:string;withdrawn?:Set<string>}){
 const [open,setOpen]=useState<string|null>(null);
 const zones=group.rows.some(r=>r.zone);
 return <section className="group-table" aria-label={group.name}>
  <h3>{group.name}</h3>
  <table><thead><tr><th scope="col" className="num">№</th><th scope="col">Команда</th><th scope="col" className="num">И</th>
   <th scope="col" className="num wide">В</th><th scope="col" className="num wide">Н</th><th scope="col" className="num wide">П</th><th scope="col" className="num wide">Мячи</th><th scope="col" className="num wide">±</th>
   <th scope="col" className="num">О</th></tr></thead>
  <tbody>{group.rows.map(r=>{const id=r.team.entry_id;const expanded=open===id;return [
   <tr key={id} data-zone={r.zone??undefined}>
    <td className="num">{r.place}{r.tied?'*':''}</td>
    <td><button type="button" className="row-toggle" aria-expanded={expanded} onClick={()=>setOpen(expanded?null:id)}>{r.team.name}{withdrawn?.has(id)&&<span className="chip">Снялась</span>}</button>
     {teamHref&&<Link className="sr-link" to={teamHref(r.team.team_id)}>Страница команды {r.team.name}</Link>}</td>
    <td className="num">{r.played}</td><td className="num wide">{r.won}</td><td className="num wide">{r.drawn}</td><td className="num wide">{r.lost}</td>
    <td className="num wide">{r.goals_for}:{r.goals_against}</td><td className="num wide">{r.goal_diff>0?`+${r.goal_diff}`:r.goal_diff}</td>
    <td className="num points">{r.points}</td></tr>,
   expanded&&<tr key={id+'-more'} className="row-more"><td/><td colSpan={3}>{`В ${r.won} · Н ${r.drawn} · П ${r.lost} · Мячи ${r.goals_for}:${r.goals_against}`}</td></tr>]})}</tbody></table>
  {group.needs_lot&&<p className="warning small" role="status">* Нужен жребий: команды равны по всем показателям.</p>}
  {zones&&advanceNote&&<p className="muted small zone-note">{advanceNote}</p>}
  <p className="muted small">{criteriaText(criteria)}</p>
 </section>;
}
