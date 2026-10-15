import {useEffect,useState} from 'react';
import {api,ApiError,errorText} from '../../api/client';
import type {AnalysisOverview,AnalysisRun,Match,MatchRatingsView,PublicMatch,PublicProtocol,Tournament} from '../../api/domain';
import {SourceStatus} from '../../components/match/SourceStatus';
import {MatchReport} from '../match-report/MatchReport';
import {publicAnalysisFromRun} from '../match-report/adapters';
import type {PlayerSelection,ReportModel,Resource} from '../match-report/model';
import type {StatGroup} from '../match-report/facts';
import {MatchRatings} from '../ratings/MatchRating';

type Sources=Pick<ReportModel,'protocol'|'cv'|'ratings'>;
const SECTIONS=[{id:'overview',label:'Обзор'},{id:'events',label:'События'},{id:'players',label:'Игроки'},{id:'stats',label:'Статистика'}];

export function publicShapeOf(m:Match,t:Tournament|null,publicProtocolId:string|null):PublicMatch{
 return {id:m.id,tournament:{id:m.tournament_id,name:t?.name??'Турнир',season:t?.season??'',starts_on:t?.starts_on??'',ends_on:t?.ends_on??'',timezone:t?.timezone??'Europe/Moscow'},
  home_name:m.home.team.name,away_name:m.away.team.name,home_team_id:m.home.team.id,away_team_id:m.away.team.id,home_logo_id:null,away_logo_id:null,
  scheduled_at:m.scheduled_at,venue_label:m.venue_label,hall:null,status:m.status,schedule_slot_s:(m.regulation_override??m.regulation.rules).schedule_slot_s,
  broadcast_url:null,broadcast_embed_url:null,public_protocol_id:publicProtocolId,
  score:{home:m.projection.effective_score.home??null,away:m.projection.effective_score.away??null}} as PublicMatch;
}

async function load<T>(read:()=>Promise<T|null>):Promise<Resource<T>>{
 try{const v=await read();return v==null?{status:'absent'}:{status:'ready',value:v}}
 catch(e){return e instanceof ApiError&&e.status===404?{status:'absent'}:{status:'error',message:errorText(e)}}
}

// Чтение в кабинете: опубликованный протокол, активная версия CV (тот же whitelist, что у сайта),
// оценки только для Админ+. Ничего не создаёт и не держит очередь протокола.
export function MatchReportTab({match:m,tournament,analytics}:{match:Match;tournament:Tournament|null;analytics:boolean}){
 const [sources,setSources]=useState<Sources>({protocol:{status:'loading'},cv:{status:'loading'},ratings:{status:'loading'}});
 const [publicId,setPublicId]=useState<string|null>(null);const [tick,setTick]=useState(0);
 const [section,setSection]=useState('overview');const [group,setGroup]=useState<StatGroup>('shots');
 const [selection,setSelection]=useState<PlayerSelection|null>(null);const [period,setPeriod]=useState('');
 useEffect(()=>{
  const controller=new AbortController();const signal=controller.signal;
  (async()=>{
   const header=m.published_version_id?await api<PublicMatch>(`/public/matches/${m.id}`,{signal}).catch(()=>null):null;
   const pid=header?.public_protocol_id??null;
   const [protocol,cv,ratings]=await Promise.all([
    load(async()=>pid?api<PublicProtocol>(`/public/protocols/${pid}`,{signal}):null),
    load(async()=>{const o=await api<AnalysisOverview>(`/matches/${m.id}/analysis`,{signal});const rid=o.active_run_id??o.published_run_id;
     return rid?publicAnalysisFromRun(await api<AnalysisRun>(`/matches/${m.id}/analysis/runs/${rid}`,{signal})):null}),
    analytics?load(async()=>{const r=await api<MatchRatingsView>(`/matches/${m.id}/ratings`,{signal});return r.snapshot_id?r:null}):Promise.resolve({status:'absent'} as Resource<MatchRatingsView>),
   ]);
   if(!signal.aborted){setPublicId(pid);setSources({protocol,cv,ratings})}
  })();
  return()=>controller.abort();
 },[m.id,m.published_version_id,analytics,tick]);
 const model:ReportModel={...sources,context:{matchId:m.id,protocolPublicId:publicId,cvRunId:sources.cv.status==='ready'?sources.cv.value.run_id:null,
  ratingSnapshotId:sources.ratings.status==='ready'?sources.ratings.value.snapshot_id:null,historicalRating:false,periodKey:period}};
 return <div className="report-tab">
  <SourceStatus label="Отчёт в кабинете" detail="Протокол — опубликованная версия; видеоанализ — активная версия кабинета; оценки — последний частный срез. Гости видят только опубликованное."/>
  <div className="report-sections" role="group" aria-label="Раздел отчёта">{SECTIONS.map(s=><button key={s.id} aria-pressed={section===s.id} onClick={()=>setSection(s.id)}>{s.label}</button>)}</div>
  <MatchReport match={publicShapeOf(m,tournament,publicId)} model={model} section={section} group={group} selection={selection}
   onSelect={setSelection} onClose={()=>setSelection(null)} onPeriod={setPeriod} onGroup={setGroup} onRetry={()=>setTick(n=>n+1)}
   onCurrentEdition={()=>undefined} historyHref={pid=>`/players/${pid}/analysis?tournament_id=${m.tournament_id}`}/>
  {analytics&&<MatchRatings matchId={m.id} refresh={tick}/>}
 </div>;
}
