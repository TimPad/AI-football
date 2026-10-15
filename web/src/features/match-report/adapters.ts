import type {AnalysisRun,MatchRatingsView,PublicAnalysis,PublicProtocol} from '../../api/domain';
import type {PlayerOrigin,ReportContext} from './model';

type Side='home'|'away';
type CvPlayer=PublicAnalysis['players'][number];
type RatingRow=MatchRatingsView['items'][number];
export type RosterRow={
 playerId:string;name:string;shirtNumber:string|null;side:Side|null;
 sources:PlayerOrigin[];cv:CvPlayer|null;rating:RatingRow|null;
};

// Публичный API не раскрывает источники карты рейтинга, поэтому совместимость не доказуема.
export function canAttachCurrentCv(context:ReportContext,origin:PlayerOrigin):boolean{
 return origin!=='rating'&&context.cvRunId!==null;
}

export function periodLabel(key:string,name:string,partial:boolean):string{
 return key==='all'&&partial?'Обработанный фрагмент':name;
}

// Соединение только по UUID; имя и номер — подписи выбранного источника.
export function mergeRoster({protocol,cv,ratings,teams}:{protocol:PublicProtocol|null;cv:PublicAnalysis|null;
 ratings:MatchRatingsView|null;teams:{home:string;away:string}}):RosterRow[]{
 const rows=new Map<string,RosterRow>();
 const row=(playerId:string,name:string,side:Side|null)=>{
  let value=rows.get(playerId);
  if(!value){value={playerId,name,shirtNumber:null,side,sources:[],cv:null,rating:null};rows.set(playerId,value);}
  return value;
 };
 for(const p of protocol?.lineup??[]){
  const value=row(p.player_id,p.display_name,p.side);value.shirtNumber=p.shirt_number;value.sources.push('protocol');
 }
 for(const p of cv?.players??[]){
  const value=row(p.player_id,p.display_name,p.side);value.cv=p;value.sources.push('cv');
  if(!value.sources.includes('protocol'))value.shirtNumber=p.shirt_number;
 }
 for(const r of ratings?.items??[]){
  const side=r.team_id===teams.home?'home':r.team_id===teams.away?'away':null;
  const value=row(r.player_id,r.display_name,side);value.rating=r;value.sources.push('rating');
  if(!value.sources.includes('protocol'))value.name=r.display_name;
 }
 const order={home:0,away:1};
 return [...rows.values()].sort((a,b)=>(a.side?order[a.side]:2)-(b.side?order[b.side]:2));
}

const PLAYER_KEYS=['distance_m','observed_s','m_per_min','hsr_m','sprints','vmax_ms','heatmap_s'] as const;
const TEAM_KEYS=['distance_m','observed_s','m_per_min','hsr_m','sprints','heatmap_s','width_m','depth_m','compactness_m2'] as const;
type Loose=Record<string,unknown>;
const pick=(source:Loose|undefined,keys:readonly string[])=>Object.fromEntries(keys.map(k=>[k,source?.[k]??null]));

// Кабинетный предпросмотр: тот же whitelist, что и серверный public_analysis, без треков и evidence.
export function publicAnalysisFromRun(run:AnalysisRun):PublicAnalysis{
 const report=run.report as Loose;const manifest=run.manifest as Loose;
 const pitch=(report.pitch??{}) as Loose;const match=(report.match??{}) as Loose;
 const periods=((report.periods??[]) as Loose[]).map(p=>{
  const teams=Object.fromEntries(Object.entries((p.teams??{}) as Record<string,Loose>).filter(([side])=>side==='A'||side==='B')
   .map(([side,values])=>{
    const kept=pick(values,TEAM_KEYS);
    const notes=Object.fromEntries(Object.entries(kept).filter(([,v])=>v===null)
     .map(([k])=>[k,values.observed_s?'Недостаточно данных':'Нет наблюдений команды']));
    return [side,{...kept,low_data:Boolean(values.low_data),metric_notes:notes}];
   }));
  return {key:p.key,name:p.name,duration_s:p.duration_s,teams};
 });
 return {match_id:run.match_id,run_id:run.id,
  pitch:{length_m:pitch.length_m,width_m:pitch.width_m,cell_m:pitch.cell_m,orientation:pitch.orientation??'camera'},
  teams:((run.context as Loose).teams??{}) as PublicAnalysis['teams'],side_map:run.side_map,
  primary_period_key:String(manifest.primary_period_key),
  video_s:Number((manifest.source_video as Loose|undefined)?.duration_s),processed_s:Number(match.processed_s),
  partial:run.partial,periods,
  players:run.players.map(p=>({player_id:p.player_id,display_name:p.display_name,shirt_number:p.shirt_number,side:p.side,
   metrics:pick(p.metrics as Loose,PLAYER_KEYS) as CvPlayer['metrics']}))};
}
