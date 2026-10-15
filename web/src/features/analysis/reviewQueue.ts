import type {AnalysisAssignment,AnalysisOverview,AnalysisRun} from '../../api/domain';

export type JobResult='not_uploaded'|'review'|'confirmed';
export const JOB_LABEL:Record<JobResult,string>={not_uploaded:'Результат не загружен',review:'На проверке',confirmed:'Подтверждён'};

// Статус задания — только по его собственным импортам; телеметрии внешней программы нет.
export function jobResultState(jobId:string,runs:AnalysisOverview['runs']):JobResult{
 const own=runs.filter(r=>r.job_id===jobId);
 return own.some(r=>r.status==='confirmed')?'confirmed':own.length?'review':'not_uploaded';
}

export type TrackFilter='all'|'unassigned'|'assigned'|'excluded';
export const TRACK_FILTERS:{id:TrackFilter;label:string}[]=[{id:'unassigned',label:'Не назначены'},{id:'assigned',label:'Назначены'},{id:'excluded',label:'Исключены'},{id:'all',label:'Все'}];
export function trackState(assignments:readonly AnalysisAssignment[],trackId:number):Exclude<TrackFilter,'all'>{
 const a=assignments.find(x=>x.track_id===trackId);
 return a?.player_id?'assigned':a&&a.excluded_reason!=null?'excluded':'unassigned';
}

// Фильтр и страница меняют только видимость; полный набор назначений хранит черновик.
export function visibleTrackIds(run:AnalysisRun,filter:TrackFilter,page:number,pageSize:number,
 assignments:readonly AnalysisAssignment[]=run.assignments):number[]{
 const ids=run.tracks.map(t=>t.track_id).filter(id=>filter==='all'||trackState(assignments,id)===filter);
 const start=Math.max(0,page-1)*pageSize;
 return ids.slice(start,start+pageSize);
}
export function filteredCount(run:AnalysisRun,filter:TrackFilter,assignments:readonly AnalysisAssignment[]=run.assignments){
 return run.tracks.filter(t=>filter==='all'||trackState(assignments,t.track_id)===filter).length;
}
