import {useState} from 'react';
import type {AnalysisRun,AnalysisAssignment} from '../../api/domain';
import type {IdentitySuggestion} from './understandingTypes';
import {SHORT_S,assignGroup,baseGroups,candidatesOf,clashes,decisionOf,overlaps,suggestionOf,type Candidate} from './candidates';

const clock=(s:number)=>`${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;

// Сопоставление по кандидатам-игрокам: один выбор на цепочку треков вместо выбора на каждый трек.
// Разделить и объединить — правка группировки в браузере; сохраняются только назначения треков.
export function PlayerCandidates({run,assignments,sideMap,disabled,suggestions,onChange}:{run:AnalysisRun;assignments:AnalysisAssignment[];
 sideMap:AnalysisRun['side_map'];disabled:boolean;suggestions:IdentitySuggestion[];onChange:(next:AnalysisAssignment[])=>void}){
 const [groups,setGroups]=useState(()=>baseGroups(run));
 const candidates=candidatesOf(run,groups);
 const start=(id:number)=>run.tracks.find(t=>t.track_id===id)?.intervals[0]?.[0]??0;
 const dur=(id:number)=>run.tracks.find(t=>t.track_id===id)?.intervals.reduce((sum,[a,b])=>sum+b-a,0)??0;
 const clash=clashes(run,candidates,assignments);
 const ready=candidates.map(c=>({c,s:suggestionOf(c.trackIds,suggestions)})).filter(x=>x.s&&decisionOf(assignments,x.c.trackIds).kind==='none');
 function split(c:Candidate){setGroups(g=>[...g.filter(ids=>ids.join('-')!==c.key),...c.trackIds.map(id=>[id])])}
 function merge(c:Candidate,otherKey:string){const other=candidates.find(x=>x.key===otherKey);if(!other)return;
  const ids=[...c.trackIds,...other.trackIds].sort((a,b)=>start(a)-start(b));
  setGroups(g=>[...g.filter(x=>![c.key,other.key].includes(x.join('-'))),ids])}
 const roster=(team:'A'|'B')=>run.context.rosters.filter(p=>p.side===sideMap[team]);
 const name=(id:string)=>run.context.rosters.find(p=>p.player_id===id);
 const thumb=(id:number)=>run.tracks.find(t=>t.track_id===id)?.thumb
  ?<img key={id} className="track-thumb small" src={`/api/v1/matches/${run.match_id}/analysis/runs/${run.id}/thumbs/${id}`} alt={`Фрагмент ${id}`}/>:null;
 const card=(c:Candidate)=>{const d=decisionOf(assignments,c.trackIds);const s=suggestionOf(c.trackIds,suggestions);const partner=clash.get(c.key);
  const mergeable=candidates.filter(o=>o.key!==c.key&&o.team===c.team&&!overlaps(run,c.trackIds,o.trackIds));
  const longest=[...c.trackIds].sort((a,b)=>dur(b)-dur(a)).slice(0,4);
  return <li key={c.key} className={`candidate${d.kind==='player'||d.kind==='excluded'?' done':''}`}>
   <div className="candidate-thumbs">{longest.map(thumb)}</div>
   <div className="candidate-body">
    <p className="candidate-meta"><b>{c.trackIds.length>1?`${c.trackIds.length} фрагмента`:'1 фрагмент'}</b> · на площадке {clock(c.seconds)} · {clock(c.span[0])}–{clock(c.span[1])}
     {c.goalkeeper&&<span className="chip">вероятно вратарь</span>}</p>
    {s&&d.kind==='none'&&<p className="candidate-hint">По номеру: №{s.number} · {name(s.player_id!)?.display_name} <button type="button" disabled={disabled} onClick={()=>onChange(assignGroup(assignments,c.trackIds,s.player_id!))}>Принять</button></p>}
    {d.kind==='mixed'&&<p className="warning small">Фрагменты назначены по-разному — выберите одно решение для всего кандидата или разделите его.</p>}
    {partner&&<p className="warning small">Этот игрок уже назначен кандидату, который виден одновременно с этим.</p>}
    <div className="row wrap candidate-actions">
     <select aria-label={`Игрок кандидата ${c.key}`} disabled={disabled} value={d.kind==='player'?d.playerId:d.kind==='excluded'?'exclude':''} onChange={e=>onChange(assignGroup(assignments,c.trackIds,e.target.value))}>
      <option value="">{d.kind==='mixed'?'Разные решения':'Не назначен'}</option>
      {roster(c.team).map(p=><option key={p.player_id} value={p.player_id}>{p.shirt_number??'—'} · {p.display_name}</option>)}
      <option value="exclude">Не игрок: судья, зритель, ошибка</option></select>
     {c.trackIds.length>1&&<button type="button" disabled={disabled} onClick={()=>split(c)}>Разделить</button>}
     {mergeable.length>0&&<select aria-label={`Объединить кандидата ${c.key}`} disabled={disabled} value="" onChange={e=>merge(c,e.target.value)}>
      <option value="">Объединить с…</option>{mergeable.map(o=><option key={o.key} value={o.key}>{clock(o.span[0])}–{clock(o.span[1])} · {o.trackIds.length} фрагм.</option>)}</select>}
    </div></div></li>};
 const others=run.tracks.filter(t=>!(t.team&&(t.role==='player'||t.role==='goalkeeper')));
 return <div className="player-candidates">
  {ready.length>0&&<div className="candidate-accept"><span>Номер прочитан у {ready.length} {ready.length===1?'кандидата':'кандидатов'}.</span>
   <button type="button" className="primary" disabled={disabled} onClick={()=>onChange(ready.reduce((acc,x)=>assignGroup(acc,x.c.trackIds,x.s!.player_id!),assignments))}>Принять все подсказки</button></div>}
  <div className="candidate-columns">{(['A','B'] as const).map(team=>{const list=candidates.filter(c=>c.team===team);
   const main=list.filter(c=>c.seconds>=SHORT_S),short=list.filter(c=>c.seconds<SHORT_S);
   const done=list.filter(c=>['player','excluded'].includes(decisionOf(assignments,c.trackIds).kind)).length;
   return <section key={team} aria-label={`Кандидаты команды ${team}`}>
    <h3>{run.context.teams[sideMap[team]].name} <span className="muted small">· назначено {done} из {list.length}</span></h3>
    <ul className="candidate-list">{main.map(card)}</ul>
    {short.length>0&&<details><summary>Короткие фрагменты · {short.length}</summary><ul className="candidate-list">{short.map(card)}</ul></details>}
   </section>})}</div>
  {others.length>0&&<p className="muted small">Судьи и треки без команды ({others.length}) игрокам не назначаются; при необходимости их можно исключить в режиме «По фрагментам».</p>}
 </div>;
}
