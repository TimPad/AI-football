import type {MatchRatingsView,PublicAnalysis} from '../../api/domain';
import {roles,num} from '../ratings/types';
import type {PlayerSelection} from './model';
import {GROUP_FACTS,MOVEMENT,factLabel,formatFact,type StatGroup} from './facts';

type RatingRow=MatchRatingsView['items'][number];
type Select=(s:PlayerSelection)=>void;

function NameButton({id,name,origin,onSelect,selected}:{id:string;name:string;origin:PlayerSelection['origin'];onSelect:Select;selected:boolean}){
 return <button className="link-button" aria-pressed={selected} onClick={()=>onSelect({playerId:id,origin})}>{name}</button>;
}

// Строки — по UUID игрока и роли; номер и имя только подписи.
export function PlayerTable({group,ratings,cv,teamName,selectedId,onSelect}:{group:StatGroup;ratings:MatchRatingsView|null;
 cv:PublicAnalysis|null;teamName:(row:{team_id?:string;side?:string|null})=>string;selectedId:string|null;onSelect:Select}){
 if(group==='movement'){
  if(!cv)return <p className="muted">Перемещения появятся после публикации видеоанализа.</p>;
  return <div className="table-scroll"><table className="stat-table" aria-label="Показатели игроков"><thead><tr><th>#</th><th>Игрок</th><th>Команда</th>
   {MOVEMENT.map(m=><th key={m.key}>{m.label}</th>)}</tr></thead><tbody>{cv.players.map(p=>
   <tr key={p.player_id} aria-selected={p.player_id===selectedId}><td className="num">{p.shirt_number??'—'}</td>
    <td><NameButton id={p.player_id} name={p.display_name} origin="cv" onSelect={onSelect} selected={p.player_id===selectedId}/></td>
    <td>{teamName(p)}</td>{MOVEMENT.map(m=><td key={m.key} className="num">{num(p.metrics[m.key])}</td>)}</tr>)}</tbody></table>
   <p className="muted small">Физическая работа относится к наблюдаемому видео; вес в оценке 0.</p></div>;
 }
 if(!ratings)return <p className="muted">Показатели этой группы берутся из опубликованных оценок; издание ещё не опубликовано.</p>;
 const keys=GROUP_FACTS[group];
 return <div className="table-scroll"><table className="stat-table" aria-label="Показатели игроков"><thead><tr><th>Игрок</th><th>Команда</th><th>Роль</th>
  {keys.map(k=><th key={k}>{factLabel(k)}</th>)}<th>Оценка</th></tr></thead><tbody>{ratings.items.map((r:RatingRow)=>
  <tr key={`${r.player_id}:${r.role}`} aria-selected={r.player_id===selectedId}>
   <td><NameButton id={r.player_id} name={r.display_name} origin="rating" onSelect={onSelect} selected={r.player_id===selectedId}/></td>
   <td>{teamName(r)}</td><td>{roles[r.role as keyof typeof roles]??r.role}</td>
   {keys.map(k=>{const f=formatFact(k,r.facts);return <td key={k} className="num">{f.text}{f.note&&<small>{f.note}</small>}</td>})}
   <td className="num strong">{r.display_rating==null?'—':r.display_rating.toFixed(1)}</td></tr>)}</tbody></table>
  <p className="muted small">Значения — сохранённые факты выбранного издания по роли игрока. Неизвестное не превращается в ноль.</p></div>;
}
