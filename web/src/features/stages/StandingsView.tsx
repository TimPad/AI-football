import type {PairView,Standings,StageView} from './api';
import {GroupTable} from './GroupTable';
import {Bracket} from './Bracket';
import {GroupMatches} from './GroupMatches';

function advanceNote(next?:StageView){
 if(!next)return undefined;
 return next.kind==='single_elim'||next.kind==='double_elim'?'Отмеченные команды выходят в плей-офф':`Отмеченные команды выходят в этап «${next.name}»`;
}

export function StageBlock({stage,next,timezone,teamHref,matchHref,action}:{stage:StageView;next?:StageView;timezone:string;teamHref?:(id:string)=>string;matchHref?:(id:string)=>string;action?:(pair:PairView)=>React.ReactNode}){
 const elimination=stage.kind==='single_elim'||stage.kind==='double_elim';
 const rounds=stage.sections[0]?.rounds??[];
 const sunk=new Set(stage.withdrawn.filter(w=>w.rule==='walkover').map(w=>w.team.entry_id));
 const annulled=stage.withdrawn.filter(w=>w.rule==='annul');
 return <div className="stage-block">
  {stage.groups.length>0&&<div className="groups-grid">{stage.groups.map(g=><div key={g.group_no} className="group-column">
   <GroupTable group={g} criteria={stage.criteria} teamHref={teamHref} advanceNote={advanceNote(next)} withdrawn={sunk}/>
   {!elimination&&<GroupMatches rounds={rounds} group={stage.kind==='groups'?g.group_no:null} timezone={timezone} matchHref={matchHref}/>}</div>)}</div>}
  {annulled.map(w=><p key={w.team.entry_id} className="muted small">{w.team.name} снялась, её результаты аннулированы.</p>)}
  {elimination&&<Bracket sections={stage.sections} timezone={timezone} matchHref={matchHref} action={action}/>}
  {elimination&&stage.withdrawn.map(w=><p key={w.team.entry_id} className="muted small">{w.team.name} снялась: соперник прошёл дальше технической победой.</p>)}
  {action&&!elimination&&rounds.some(r=>r.pairs.some(p=>p.changed))&&<div className="pair-actions">{rounds.flatMap(r=>r.pairs.filter(p=>p.changed)).map(p=><div key={p.key}>{p.label}: {action(p)}</div>)}</div>}
 </div>;
}

export function StandingsView({data,timezone,teamHref,matchHref,action,empty}:{data:Standings;timezone:string;teamHref?:(id:string)=>string;matchHref?:(id:string)=>string;action?:(pair:PairView)=>React.ReactNode;empty?:React.ReactNode}){
 if(!data.stages.length)return <>{empty}</>;
 return <div className="standings">{data.stages.map((stage,i)=><div key={stage.id??stage.position}>
  {data.stages.length>1&&<h2>{stage.name}</h2>}
  <StageBlock stage={stage} next={data.stages[i+1]} timezone={timezone} teamHref={teamHref} matchHref={matchHref} action={action}/></div>)}</div>;
}
