import type {AnalysisRun} from '../../api/domain';
import type {components} from '../../api/types';
import {api} from '../../api/client';
import {useLoad,Loading} from '../../components/ui';
import {useRatingCommand,CommandStatus} from '../ratings/commands';
export const teamTaskStatuses:Record<string,string>={open:'У капитана',team_confirmed:'Команда подтверждена',needs_material_fix:'Нужны исправления материала',obsolete:'Задание устарело',revoked:'Задание отозвано'};
export function TeamReviewPanel({run,actorId,onChanged}:{run:AnalysisRun,actorId:string,onChanged:()=>void}){
 const base=`/matches/${run.match_id}/analysis/runs/${run.id}`;const state=useLoad(()=>api<components['schemas']['TeamTaskList']>(`${base}/team-review-tasks`),`${run.id}:${run.revision}`);
 const command=useRatingCommand(`aifootball:team-task:${actorId}:${run.id}`,()=>{state.reload();onChanged()});
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;
 return <section className="surface"><h2>Подтверждение игроков командами</h2><p className="muted">Капитан самостоятельно подтверждает игроков своей команды. Затем Админ+ проверяет качество аналитики и публикует результат отдельным действием.</p>{!run.side_map_verified&&<p className="warning">Сначала проверьте и сохраните соответствие команд A/B ниже.</p>}
  <div className="form-grid">{(['home','away'] as const).map(side=>{const team=run.context.teams[side];const tasks=state.data!.items.filter(t=>t.side===side);const latest=tasks[0];return <article key={side}><h3>{team.name}</h3><p>{latest?teamTaskStatuses[latest.status]:'Не выдано'}</p>{latest?.reason&&<p className="muted">{latest.reason}</p>}<button disabled={command.locked||run.status!=='review'||!run.side_map_verified||latest?.status==='open'||latest?.status==='needs_material_fix'} onClick={()=>void command.execute(`${base}/team-review-tasks`,{team_id:team.id,expected_run_revision:run.revision})}>Выдать проверку {team.name}</button>{tasks.length>1&&<details><summary>История заданий · {tasks.length}</summary>{tasks.map(t=><p key={t.id}>{teamTaskStatuses[t.status]} · {t.confirmed_by_kind==='captain'?'Капитан':t.confirmed_by_kind==='admin'?'Админ+':'Без подтверждения'}</p>)}</details>}</article>})}</div><CommandStatus command={command}/>
 </section>;
}
