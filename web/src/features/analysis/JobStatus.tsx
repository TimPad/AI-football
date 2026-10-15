import type {AnalysisOverview} from '../../api/domain';
import {JOB_LABEL,jobResultState} from './reviewQueue';

// Метка выданного задания и отдельные отметки активной/опубликованной версии.
export function JobStatus({jobId,overview}:{jobId:string;overview:AnalysisOverview}){
 const state=jobResultState(jobId,overview.runs);const own=overview.runs.filter(r=>r.job_id===jobId);
 const reviews=own.filter(r=>r.status==='review').length;
 return <span className="job-status">
  <span className={`chip ${state==='confirmed'?'ok':state==='review'?'warn':''}`}>{JOB_LABEL[state]}</span>
  {state==='confirmed'&&reviews>0&&<span className="chip warn">ещё на проверке: {reviews}</span>}
  {own.some(r=>r.id===overview.active_run_id)&&<span className="chip">активная версия</span>}
  {own.some(r=>r.id===overview.published_run_id)&&<span className="chip ok">опубликована</span>}
 </span>;
}
