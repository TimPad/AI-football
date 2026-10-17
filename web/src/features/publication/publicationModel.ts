import type {AnalysisOverview,Match,Version} from '../../api/domain';
import type {Analytics,Actions,Participation} from '../ratings/types';

export type Blocker={text:string;href:string};
export type PublicationBlock={currentLabel:string;selectedLabel:string|null;blockers:Blocker[]};
const short=(id:string)=>id.slice(0,8);
export const when=(iso:string)=>new Date(iso).toLocaleString('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});

// Отдельные блоки без общей «ревизии всех источников»; сервер остаётся источником правил.
export function protocolBlock(match:Match,versions:Version[],selected:string|null):PublicationBlock{
 const current=versions.find(v=>v.id===match.published_version_id);
 const chosen=versions.find(v=>v.id===selected);
 const blockers:Blocker[]=[];
 if(!versions.length)blockers.push({text:'Нет подтверждённой версии протокола',href:'?tab=protocol'});
 return {currentLabel:current?`версия ${current.number} · ${when(current.published_at??current.confirmed_at)}`:'Не опубликован',
  selectedLabel:chosen?`версия ${chosen.number} · подтверждена ${when(chosen.confirmed_at)}`:null,blockers};
}

export function cvBlock(overview:AnalysisOverview,selected:string|null):PublicationBlock{
 const runs=overview.runs;const current=runs.find(r=>r.id===overview.published_run_id);const chosen=runs.find(r=>r.id===selected);
 const blockers:Blocker[]=[];
 if(!runs.some(r=>r.status==='confirmed'))blockers.push({text:runs.length?'Версия на проверке не подтверждена':'Результат видеоанализа не загружен',href:'?tab=review'});
 if(chosen&&!chosen.passed)blockers.push({text:'Проверка качества не пройдена',href:`?tab=review&run_id=${chosen.id}`});
 return {currentLabel:current?`от ${when(current.created_at)} · ${current.partial?'фрагмент':'весь матч'}`:'Не опубликован',
  selectedLabel:chosen?`от ${when(chosen.created_at)} · ${chosen.status==='confirmed'?'подтверждена':'на проверке'}`:null,blockers};
}

export function performanceBlock(match:Match,part:Participation,actions:Actions,saved:{participation_version_id:string|null;action_version_id:string|null;policy_approved:boolean}):PublicationBlock{
 const blockers:Blocker[]=[];
 if(!match.published_version_id)blockers.push({text:'Сначала опубликуйте протокол',href:'?tab=publication'});
 if(!part.versions.some(v=>v.status==='confirmed'))blockers.push({text:'Нет подтверждённого участия',href:'?tab=participation'});
 if(!actions.versions.some(v=>v.status==='confirmed'))blockers.push({text:'Нет подтверждённых действий',href:'?tab=actions'});
 const label=(kind:string,id:string|null,list:{id:string;revision:number}[])=>id?`${kind} №${list.find(v=>v.id===id)?.revision??short(id)}`:`${kind} не выбрано`;
 return {currentLabel:saved.participation_version_id||saved.action_version_id?`${label('участие',saved.participation_version_id,part.versions)} · ${label('действия',saved.action_version_id,actions.versions)}${saved.policy_approved?' · методика разрешена':''}`:'Источники не разрешены',
  selectedLabel:null,blockers};
}

export function ratingBlock(analytics:Analytics,tournamentId:string):PublicationBlock&{candidate:Analytics['snapshots'][number]|null}{
 const published=analytics.snapshots.find(s=>s.snapshot_id===analytics.public_snapshot_id&&s.published_at);
 const latest=analytics.snapshots.filter(s=>s.scope==='public').sort((a,b)=>b.calculated_at.localeCompare(a.calculated_at))[0];
 const candidate=latest&&!latest.published_at?latest:null;
 const blockers:Blocker[]=[];
 if(published?.stale||latest?.stale)blockers.push({text:'Источники изменились — нужен новый расчёт',href:`/tournaments/${tournamentId}?tab=ratings`});
 if(!analytics.policy_approved)blockers.push({text:'Методика не разрешена для сайта',href:'?tab=publication'});
 return {currentLabel:published?`опубликован ${when(published.published_at!)}`:'Не опубликован',
  selectedLabel:candidate?`новый расчёт от ${when(candidate.calculated_at)}${candidate.stale?' · устарел':''}`:null,blockers,candidate};
}
