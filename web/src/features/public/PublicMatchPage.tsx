import {useEffect,useRef,useState} from 'react';
import {useDocumentTitle} from '../../components/useDocumentTitle';
import {Link,useLocation,useParams} from 'react-router-dom';
import {useQueryPatch} from '../navigation/useQueryPatch';
import {api} from '../../api/client';
import type {PublicMatch} from '../../api/domain';
import {Loading} from '../../components/ui';
import {MatchHeader} from '../../components/match/MatchHeader';
import {SectionNavigation} from '../../components/match/SectionNavigation';
import {isUuid,patchQuery,readMatchTab} from '../navigation/query';
import {MatchReport} from '../match-report/MatchReport';
import type {PlayerOrigin,ReportModel} from '../match-report/model';
import {STAT_GROUPS,type StatGroup} from '../match-report/facts';
import {resultNote} from '../protocol/PublicProtocolContent';
import {loadPublicSection,SECTION_SOURCES} from './matchLoader';
import {publicBack} from '../navigation/publicContext';
import {Broadcast} from './Broadcast';
import {MatchAside} from './MatchAside';
import {goalScorers} from '../match-report/MatchTimeline';

const SECTIONS=[{id:'overview',label:'Обзор'},{id:'events',label:'События'},{id:'players',label:'Составы'},{id:'stats',label:'Статистика'},{id:'video',label:'Видео'}];
// Вкладка без содержимого не показывается: события — из опубликованного протокола, видео — из ссылки на трансляцию.
const hasSection=(match:PublicMatch,id:string)=>id==='events'?!!match.public_protocol_id:id==='video'?!!(match.broadcast_url||match.broadcast_embed_url):true;
const ORIGINS:PlayerOrigin[]=['protocol','cv','rating'];
type Sources=Pick<ReportModel,'protocol'|'cv'|'ratings'|'actions'>;
const EMPTY:Sources={protocol:{status:'loading'},cv:{status:'loading'},ratings:{status:'loading'},actions:{status:'loading'}};

export function PublicMatchPage(){
 const {id=''}=useParams();
 if(!isUuid(id))return <div className="block-error" role="alert">Неверная ссылка на матч.</div>;
 return <MatchContent key={id} id={id}/>;
}

function MatchContent({id}:{id:string}){
 const location=useLocation();const href=location.pathname+location.search;const back=publicBack(location.state,href,['team','tournament','calendar'],{href:'/',label:'← К календарю матчей'});
 const [params,update]=useQueryPatch();
 const [match,setMatch]=useState<PublicMatch>();const [error,setError]=useState<unknown>();const [tick,setTick]=useState(0);
 const requested=readMatchTab(params,'public');
 const snapshotParam=isUuid(params.get('snapshot_id'))?params.get('snapshot_id'):null;
 const playerId=isUuid(params.get('player_id'))?params.get('player_id'):null;
 const origin=(ORIGINS as string[]).includes(params.get('origin')??'')?params.get('origin') as PlayerOrigin:'protocol';
 // Без выбора в URL группа определяется доступными источниками внутри отчёта.
 const group=(STAT_GROUPS.find(g=>g.id===params.get('group'))?.id??null) as StatGroup|null;
 const period=/^(all|[1-9][0-9]?)$/.test(params.get('period')??'')?params.get('period')!:'all';
 const tab=match&&!hasSection(match,requested)?'overview':requested;
 useDocumentTitle(match?`${match.home_name} — ${match.away_name}`:null);
 // Командная сводка действий зависит от периода только во вкладке «Статистика»; обзор — всегда весь матч.
 const actionsPeriod=tab==='stats'?period:'all';
 const [sources,setSources]=useState<Sources>(EMPTY);
 const loadedKey=useRef('');

 useEffect(()=>{
  const controller=new AbortController();setError(undefined);
  api<PublicMatch>(`/public/matches/${id}`,{signal:controller.signal}).then(setMatch).catch(e=>{if(!controller.signal.aborted)setError(e)});
  return()=>controller.abort();
 },[id,tick]);

 // Ответ прежнего раздела/издания не подставляется: отмена + сверка ключа контекста.
 useEffect(()=>{
  if(!match)return;
  const key=`${match.id}|${snapshotParam??''}|${tick}|${actionsPeriod}`;
  if(loadedKey.current!==key){loadedKey.current=key;setSources(EMPTY)}
  const needed=SECTION_SOURCES[tab]??[];if(!needed.length)return;
  const controller=new AbortController();
  loadPublicSection(match,tab,snapshotParam,controller.signal,actionsPeriod).then(value=>{
   if(controller.signal.aborted||loadedKey.current!==key)return;
   setSources(current=>({...current,...value}));
  }).catch(()=>{});
  return()=>controller.abort();
 },[match,tab,snapshotParam,tick,actionsPeriod]);

 const navigate=(patch:Record<string,string|null>,replace=false)=>update(patch,{replace});
 if(!match)return <Loading error={error} retry={()=>setTick(v=>v+1)}/>;
 const ratingsSnapshot=sources.ratings.status==='ready'?sources.ratings.value.snapshot_id:null;
 const model:ReportModel={...sources,context:{matchId:match.id,protocolPublicId:match.public_protocol_id,
  cvRunId:sources.cv.status==='ready'?sources.cv.value.run_id:null,ratingSnapshotId:snapshotParam??ratingsSnapshot,
  historicalRating:snapshotParam!==null,periodKey:period}};
 const note=sources.protocol.status==='ready'?resultNote(sources.protocol.value):null;
 return <>
  <Link className="breadcrumb" to={back.href} state={back.state}>{back.label}</Link>
  <MatchHeader match={match} resultNote={note} scorers={sources.protocol.status==='ready'?goalScorers(sources.protocol.value):null}>
   <SectionNavigation label="Разделы матча" items={SECTIONS.filter(s=>hasSection(match,s.id))} selected={tab} onSelect={value=>navigate({tab:value})}
    href={value=>`?${patchQuery(params,{tab:value})}`}/>
  </MatchHeader>
  <MatchReport match={match} model={model} section={tab} group={group}
   selection={playerId?{playerId,origin}:null}
   onSelect={s=>navigate({player_id:s.playerId,origin:s.origin,snapshot_id:s.origin==='rating'?model.context.ratingSnapshotId:snapshotParam})}
   onClose={()=>navigate({player_id:null,origin:null})}
   onPeriod={key=>navigate({period:key},true)} onGroup={g=>navigate({group:g},true)}
   onRetry={()=>setTick(v=>v+1)} onCurrentEdition={()=>navigate({snapshot_id:null})}
   historyHref={pid=>`/watch/players/${pid}?${new URLSearchParams({tournament_id:match.tournament.id,
    ...(model.context.ratingSnapshotId?{snapshot_id:model.context.ratingSnapshotId}:{})})}`}
   video={<Broadcast match={match}/>} aside={<MatchAside match={match}/>}/>
 </>;
}
