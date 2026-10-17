import type {AnalysisRun,AnalysisAssignment} from '../../api/domain';
import type {IdentitySuggestion} from './understandingTypes';

// Кандидат-игрок — цепочка треков одного человека из склейки (run.groups) или одиночный трек.
// Назначение кандидата раскладывается на его треки: сервер по-прежнему хранит решения по трекам.
export type Candidate={key:string;team:'A'|'B';trackIds:number[];seconds:number;span:[number,number];goalkeeper:boolean};
export type GroupDecision={kind:'none'|'player'|'excluded'|'mixed';playerId?:string};
type Track=AnalysisRun['tracks'][number];

// Дубль трекера при передаче игрока между треками — до секунды (как OVERLAP_S на сервере).
export const HANDOFF_S=1;
export const SHORT_S=10;

const playable=(t:Track)=>!!t.team&&(t.role==='player'||t.role==='goalkeeper');
const seconds=(t:Track)=>t.intervals.reduce((s,[a,b])=>s+(b-a),0);

export function baseGroups(run:AnalysisRun):number[][]{
 const known=new Set(run.tracks.filter(playable).map(t=>t.track_id));
 const groups=(run.groups??[]).map(g=>g.filter(id=>known.has(id))).filter(g=>g.length>0);
 const grouped=new Set(groups.flat());
 return [...groups,...[...known].filter(id=>!grouped.has(id)).map(id=>[id])];
}

export function candidatesOf(run:AnalysisRun,groups:number[][]):Candidate[]{
 const byId=new Map(run.tracks.map(t=>[t.track_id,t]));
 return groups.map(ids=>{const tracks=ids.map(id=>byId.get(id)!).filter(Boolean);
  const total=tracks.reduce((s,t)=>s+seconds(t),0);const keeper=tracks.filter(t=>t.role==='goalkeeper').reduce((s,t)=>s+seconds(t),0);
  const starts=tracks.flatMap(t=>t.intervals.map(i=>i[0])),ends=tracks.flatMap(t=>t.intervals.map(i=>i[1]));
  return {key:ids.join('-'),team:tracks[0].team as 'A'|'B',trackIds:ids,seconds:total,span:[Math.min(...starts),Math.max(...ends)] as [number,number],goalkeeper:keeper>total/2};
 }).sort((a,b)=>b.seconds-a.seconds);
}

// Одновременно видимые больше чем на HANDOFF_S — разные люди: таких не объединяем и не даём одному игроку.
export function overlaps(run:AnalysisRun,a:number[],b:number[]):boolean{
 const spans=(ids:number[])=>run.tracks.filter(t=>ids.includes(t.track_id)).flatMap(t=>t.intervals);
 return spans(a).some(([s1,e1])=>spans(b).some(([s2,e2])=>Math.min(e1,e2)-Math.max(s1,s2)>HANDOFF_S));
}

export function decisionOf(assignments:AnalysisAssignment[],ids:number[]):GroupDecision{
 const values=ids.map(id=>assignments.find(a=>a.track_id===id));
 const key=(a:AnalysisAssignment|undefined)=>a?.player_id?`p:${a.player_id}`:a?.excluded_reason!=null?'x':'';
 const keys=new Set(values.map(key));
 if(keys.size>1)return {kind:'mixed'};
 const only=values[0];
 return only?.player_id?{kind:'player',playerId:only.player_id}:only?.excluded_reason!=null?{kind:'excluded'}:{kind:'none'};
}

// Назначение кандидата: всем его трекам — один игрок, исключение или «не назначен».
export function assignGroup(assignments:AnalysisAssignment[],ids:number[],value:string):AnalysisAssignment[]{
 const rest=assignments.filter(a=>!ids.includes(a.track_id));
 if(!value)return rest;
 return [...rest,...ids.map(track_id=>value==='exclude'?{track_id,excluded_reason:'Не игрок матча'}:{track_id,player_id:value})];
}

// Номер, прочитанный хоть на одном фрагменте, относится ко всему кандидату — если подсказки не спорят.
export function suggestionOf(ids:number[],suggestions:IdentitySuggestion[]):IdentitySuggestion|null{
 const found=suggestions.filter(s=>ids.includes(s.track_id)&&s.player_id&&s.status!=='conflict');
 const players=new Set(found.map(s=>s.player_id));
 return players.size===1?found[0]:null;
}

// Один игрок у двух кандидатов, которые видны одновременно, — сервер не подтвердит такую версию.
export function clashes(run:AnalysisRun,candidates:Candidate[],assignments:AnalysisAssignment[]):Map<string,string>{
 const out=new Map<string,string>();
 const assigned=candidates.map(c=>({c,d:decisionOf(assignments,c.trackIds)})).filter(x=>x.d.kind==='player');
 for(const x of assigned)for(const y of assigned)
  if(x.c.key<y.c.key&&x.d.playerId===y.d.playerId&&overlaps(run,x.c.trackIds,y.c.trackIds)){out.set(x.c.key,y.c.key);out.set(y.c.key,x.c.key)}
 return out;
}
