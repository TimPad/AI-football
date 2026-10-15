import {api,ApiError,errorText} from '../../api/client';
import type {MatchRatingsView,PublicAnalysis,PublicMatch,PublicProtocol,TeamActionStats} from '../../api/domain';
import type {ReportModel,Resource} from '../match-report/model';

type Source='protocol'|'cv'|'ratings'|'actions';
// Каждому разделу — только его публичные зависимости.
// Протокол нужен везде: из него шапка берёт авторов голов.
export const SECTION_SOURCES:Record<string,Source[]>={overview:['protocol','cv','ratings','actions'],events:['protocol'],
 players:['protocol','cv','ratings'],stats:['protocol','cv','ratings','actions'],video:['protocol']};

async function resource<T>(load:()=>Promise<T|null>):Promise<Resource<T>>{
 try{const value=await load();return value==null?{status:'absent'}:{status:'ready',value}}
 catch(error){
  if(error instanceof ApiError&&error.status===404)return {status:'absent'};
  return {status:'error',message:errorText(error)};
 }
}

export async function loadPublicSection(match:PublicMatch,tab:string,snapshotId:string|null,
 signal:AbortSignal,period='all'):Promise<Partial<ReportModel>>{
 signal.throwIfAborted();
 const wanted=SECTION_SOURCES[tab]??[];const options={signal};
 const loaders:Record<Source,()=>Promise<Resource<unknown>>>={
  protocol:()=>match.public_protocol_id?resource(()=>api<PublicProtocol>(`/public/protocols/${match.public_protocol_id}`,options))
   :Promise.resolve({status:'absent'}),
  cv:()=>resource(()=>api<PublicAnalysis>(`/public/matches/${match.id}/analysis`,options)),
  actions:()=>resource(()=>api<TeamActionStats>(`/public/matches/${match.id}/action-stats?period=${encodeURIComponent(period)}`,options)),
  ratings:()=>resource(async()=>{
   const query=snapshotId?`?snapshot_id=${encodeURIComponent(snapshotId)}`:'';
   const value=await api<MatchRatingsView>(`/public/matches/${match.id}/ratings${query}`,options);
   return value.snapshot_id?value:null;
  }),
 };
 const settled=await Promise.allSettled(wanted.map(source=>loaders[source]()));
 signal.throwIfAborted();
 const result:Partial<ReportModel>={};
 wanted.forEach((source,i)=>{const s=settled[i];
  (result as Record<Source,Resource<unknown>>)[source]=s.status==='fulfilled'?s.value:{status:'error',message:errorText(s.reason)}});
 return result;
}
