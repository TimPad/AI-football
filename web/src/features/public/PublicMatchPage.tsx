import {useEffect,useRef,useState} from 'react';
import {useParams} from 'react-router-dom';
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
import {Broadcast} from './Broadcast';

const SECTIONS=[{id:'overview',label:'Обзор'},{id:'events',label:'События'},{id:'players',label:'Игроки'},{id:'stats',label:'Статистика'},{id:'video',label:'Видео'}];
const ORIGINS:PlayerOrigin[]=['protocol','cv','rating'];
type Sources=Pick<ReportModel,'protocol'|'cv'|'ratings'>;
const EMPTY:Sources={protocol:{status:'loading'},cv:{status:'loading'},ratings:{status:'loading'}};

export function PublicMatchPage(){
 const {id=''}=useParams();
 if(!isUuid(id))return <div className="block-error" role="alert">Неверная ссылка на матч.</div>;
 return <MatchContent key={id} id={id}/>;
}

function MatchContent({id}:{id:string}){
 const [params,update]=useQueryPatch();
 const [match,setMatch]=useState<PublicMatch>();const [error,setError]=useState<unknown>();const [tick,setTick]=useState(0);
 const tab=readMatchTab(params,'public');
 const snapshotParam=isUuid(params.get('snapshot_id'))?params.get('snapshot_id'):null;
 const playerId=isUuid(params.get('player_id'))?params.get('player_id'):null;
 const origin=(ORIGINS as string[]).includes(params.get('origin')??'')?params.get('origin') as PlayerOrigin:'protocol';
 const group=(STAT_GROUPS.find(g=>g.id===params.get('group'))?.id??'shots') as StatGroup;
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
  const key=`${match.id}|${snapshotParam??''}|${tick}`;
  if(loadedKey.current!==key){loadedKey.current=key;setSources(EMPTY)}
  const needed=SECTION_SOURCES[tab]??[];if(!needed.length)return;
  const controller=new AbortController();
  loadPublicSection(match,tab,snapshotParam,controller.signal).then(value=>{
   if(controller.signal.aborted||loadedKey.current!==key)return;
   setSources(current=>({...current,...value}));
  }).catch(()=>{});
  return()=>controller.abort();
 },[match,tab,snapshotParam,tick]);

 const navigate=(patch:Record<string,string|null>,replace=false)=>update(patch,{replace});
 if(!match)return <Loading error={error} retry={()=>setTick(v=>v+1)}/>;
 const ratingsSnapshot=sources.ratings.status==='ready'?sources.ratings.value.snapshot_id:null;
 const model:ReportModel={...sources,context:{matchId:match.id,protocolPublicId:match.public_protocol_id,
  cvRunId:sources.cv.status==='ready'?sources.cv.value.run_id:null,ratingSnapshotId:snapshotParam??ratingsSnapshot,
  historicalRating:snapshotParam!==null,periodKey:params.get('period')??''}};
 const note=sources.protocol.status==='ready'?resultNote(sources.protocol.value):null;
 return <>
  <MatchHeader match={match} resultNote={note}>
   <SectionNavigation label="Разделы матча" items={SECTIONS} selected={tab} onSelect={value=>navigate({tab:value})}
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
   video={<Broadcast match={match}/>}/>
 </>;
}
