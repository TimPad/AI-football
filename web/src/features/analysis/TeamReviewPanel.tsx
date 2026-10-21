import type {AnalysisRun} from '../../api/domain';
import {useState} from 'react';
import type {components} from '../../api/types';
import {api} from '../../api/client';
import {useLoad,Loading,Field} from '../../components/ui';
import {useRatingCommand,CommandStatus} from '../ratings/commands';
export const teamTaskStatuses:Record<string,string>={open:'У капитана',team_confirmed:'Команда подтверждена',needs_material_fix:'Нужны исправления материала',obsolete:'Задание устарело',revoked:'Задание отозвано'};
export function TeamReviewPanel({run,actorId,onChanged}:{run:AnalysisRun,actorId:string,onChanged:()=>void}){
 const [reason,setReason]=useState('');
 const base=`/matches/${run.match_id}/analysis/runs/${run.id}`;const state=useLoad(async()=>{const [tasks,status]=await Promise.all([api<components['schemas']['TeamTaskList']>(`${base}/team-review-tasks`),api<components['schemas']['TeamSideStatuses']>(`${base}/team-confirmations`)]);return {tasks,status}},`${run.id}:${run.revision}`);
 const command=useRatingCommand(`aifootball:team-task:${actorId}:${run.id}`,()=>{state.reload();onChanged()});
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;
 return <section className="surface"><h2>Подтверждение игроков командами</h2><p className="muted">Капитан самостоятельно подтверждает игроков своей команды. Затем Админ+ проверяет качество аналитики и публикует результат отдельным действием.</p>{!run.side_map_verified&&<p className="warning">Сначала проверьте и сохраните соответствие команд A/B ниже.</p>}
  {state.data.status.sides?.every(s=>s.status==='team_confirmed')&&<p className="success">Игроки обеих команд подтверждены</p>}
  <div className="form-grid">{(['home','away'] as const).map(side=>{const team=run.context.teams[side];const tasks=state.data!.tasks.items.filter(t=>t.side===side);const latest=tasks[0];const status=state.data!.status.sides?.find(s=>s.side===side);return <article key={side}><h3>{team.name}</h3><p>{teamTaskStatuses[status?.status??latest?.status]??'Не выдано'}{status?.status==='team_confirmed'?status.actor_kind==='captain'?' · Капитан подтвердил самостоятельно':' · Подтвердил Админ+':''}</p>{latest?.reason&&<p className="muted">{latest.reason}</p>}<button disabled={command.locked||run.status!=='review'||!run.side_map_verified||latest?.status==='open'||latest?.status==='needs_material_fix'} onClick={()=>void command.execute(`${base}/team-review-tasks`,{team_id:team.id,expected_run_revision:run.revision})}>Выдать проверку {team.name}</button>
   {run.status==='review'&&<details><summary>Проверить сторону вместо капитана</summary><p className="muted">Текущие назначения сохранят авторство Админ+. Открытое задание капитана будет отозвано, его черновик останется в истории.</p><Field label={`Причина проверки ${team.name}`}><input disabled={command.locked} maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)}/></Field><button disabled={command.locked||!reason.trim()||!run.side_map_verified} onClick={()=>void command.execute(`${base}/team-confirmations`,{side,reason,expected_run_revision:run.revision})}>Подтвердить сторону {team.name} как Админ+</button></details>}
   {tasks.length>1&&<details><summary>История заданий · {tasks.length}</summary>{tasks.map(t=><p key={t.id}>{teamTaskStatuses[t.status]} · {t.confirmed_by_kind==='captain'?'Капитан':t.confirmed_by_kind==='admin'?'Админ+':'Без подтверждения'}</p>)}</details>}</article>})}</div><CommandStatus command={command}/>
 </section>;
}
