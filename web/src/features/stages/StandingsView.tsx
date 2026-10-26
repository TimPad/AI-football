import type {PairView,Standings,StageView} from './api';
import {GroupTable} from './GroupTable';
import {Bracket,PairCard} from './Bracket';

function advanceNote(stage:StageView,next?:StageView){
 if(!next)return undefined;
 return next.kind==='single_elim'||next.kind==='double_elim'?'Отмеченные команды выходят в плей-офф':`Отмеченные команды выходят в этап «${next.name}»`;
}

export function StageBlock({stage,next,timezone,teamHref,matchHref,action}:{stage:StageView;next?:StageView;timezone:string;teamHref?:(id:string)=>string;matchHref?:(id:string)=>string;action?:(pair:PairView)=>React.ReactNode}){
 const elimination=stage.kind==='single_elim'||stage.kind==='double_elim';
 return <div className="stage-block">
  <div className="groups-grid">{stage.groups.map(g=><GroupTable key={g.group_no} group={g} criteria={stage.criteria} teamHref={teamHref} advanceNote={advanceNote(stage,next)}/>)}</div>
  {elimination?<Bracket sections={stage.sections} timezone={timezone} matchHref={matchHref} action={action}/>
   :stage.sections[0]?.rounds.length?<details className="stage-rounds"><summary>Туры</summary>{stage.sections[0].rounds.map(r=><div key={r.round_no} className="tour"><h4>{r.name}</h4>
    {r.pairs.filter(p=>!p.bye).map(p=><PairCard key={p.key} pair={p} timezone={timezone} matchHref={matchHref} action={action}/>)}</div>)}</details>:null}
 </div>;
}

export function StandingsView({data,timezone,teamHref,matchHref,action,empty}:{data:Standings;timezone:string;teamHref?:(id:string)=>string;matchHref?:(id:string)=>string;action?:(pair:PairView)=>React.ReactNode;empty?:React.ReactNode}){
 if(!data.stages.length)return <>{empty}</>;
 return <div className="standings">{data.stages.map((stage,i)=><div key={stage.id??stage.position}>
  {data.stages.length>1&&<h2>{stage.name}</h2>}
  <StageBlock stage={stage} next={data.stages[i+1]} timezone={timezone} teamHref={teamHref} matchHref={matchHref} action={action}/></div>)}</div>;
}
