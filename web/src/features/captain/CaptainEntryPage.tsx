import {Link,useParams,useNavigate} from 'react-router-dom';
import {api} from '../../api/client';
import type {components} from '../../api/types';
import {useLoad,Loading,Field,Check,Empty} from '../../components/ui';
import {useDraft} from '../protocol/drafts';
import {useRatingCommand,CommandStatus} from '../ratings/commands';
import {useCaptainAuth} from './CaptainAuth';
export type Application=components['schemas']['ApplicationView'];
type Team=components['schemas']['CaptainTeamView'];
type Option=components['schemas']['CaptainTournamentOption'];
export const applicationStatuses:Record<string,string>={draft:'На подготовке',submitted:'Отправлена',changes_requested:'Требуются изменения',accepted:'Принята'};
const deadline=(t:Option)=>t.deadline?`${new Date(t.deadline).toLocaleString('ru-RU',{timeZone:t.timezone??'Europe/Moscow'})} · ${t.timezone}`:'Без срока';
const closed=(t:Option)=>!t.applications_open||!!t.deadline&&Date.parse(t.deadline)<=Date.now();

export function CaptainApplications(){const {id=''}=useParams();const {session}=useCaptainAuth();const navigate=useNavigate();
 const state=useLoad(async()=>{const [team,applications,options]=await Promise.all([api<Team>(`/captain/teams/${id}`),api<{items:Application[]}>(`/captain/teams/${id}/applications?limit=100`),api<{items:Option[]}>(`/captain/teams/${id}/tournament-options?limit=100`)]);return {team,applications:applications.items,options:options.items}},id);
 const command=useRatingCommand<Application>(`aifootball:application-create:${session!.id}:${id}`,a=>navigate(`/captain/applications/${a.id}`));
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const d=state.data;
 return <><Link className="breadcrumb" to={`/captain/teams/${id}`}>← {d.team.name}</Link><h1>Турниры и заявки</h1><p className="muted">Состав допускает организатор. Отправка заявки не создаёт турнирную команду автоматически.</p><section className="surface"><h2>Мои заявки</h2>{d.applications.length?<div className="table-scroll"><table><thead><tr><th>Турнир</th><th>Статус</th><th>Версия</th></tr></thead><tbody>{d.applications.map(a=><tr key={a.id}><td><Link to={`/captain/applications/${a.id}`}>{a.tournament.name}</Link></td><td>{applicationStatuses[a.status]}</td><td>{a.submitted_version?`№${a.submitted_version.number}`:'Черновик'}</td></tr>)}</tbody></table></div>:<Empty>Пока нет заявок. Выберите турнир ниже.</Empty>}</section>
  <section className="surface"><h2>Доступные турниры</h2><div className="captain-team-cards">{d.options.map(t=>{const existing=d.applications.find(a=>a.tournament_id===t.id);return <article key={t.id}><h3>{t.name}</h3><p className="muted">{t.season} · {closed(t)?'Подача закрыта':`Подача: ${deadline(t)}`}{t.invitation_id?' · Приглашение организатора':''}</p>{existing?<Link className="button" to={`/captain/applications/${existing.id}`}>Открыть заявку</Link>:<button disabled={closed(t)||d.team.archived||command.locked} onClick={()=>void command.execute(`/captain/tournaments/${t.id}/applications`,{team_id:id,...(t.invitation_id?{invitation_id:t.invitation_id}:{})})}>Подготовить заявку</button>}</article>})}</div><CommandStatus command={command}/></section>
 </>;
}

export function CaptainEntryPage(){const {id=''}=useParams();const state=useLoad(async()=>{const application=await api<Application>(`/captain/applications/${id}`);const team=await api<Team>(`/captain/teams/${application.team_id}`);return {application,team}},id);
 return state.data?<EntryEditor key={`${id}:${state.data.application.revision}`} {...state.data} onSaved={a=>state.setData({...state.data!,application:a})} onRefresh={state.reload}/>:<Loading error={state.error} retry={state.reload}/>;
}
type Draft={sourceRosterRevision:number,players:Record<string,string>};
function EntryEditor({application:a,team,onSaved,onRefresh}:{application:Application,team:Team,onSaved:(a:Application)=>void,onRefresh:()=>void}){
 const {session}=useCaptainAuth();const initial:Draft={sourceRosterRevision:a.draft.source_roster_revision,players:Object.fromEntries(a.draft.players.map(p=>[p.player_id,p.shirt_number??'']))};
 const draft=useDraft(`aifootball:application-draft:${session!.id}:${a.id}`,initial,(v:unknown):v is Draft=>!!v&&typeof v==='object'&&'sourceRosterRevision' in v&&'players' in v&&!!v.players&&typeof v.players==='object');const d=draft.value;
 const dirty=JSON.stringify(d)!==JSON.stringify(initial);const command=useRatingCommand<Application>(`aifootball:application-command:${session!.id}:${a.id}`,value=>{draft.clear();onSaved(value)});
 const locked=command.locked||draft.corrupt||team.archived||a.tournament.archived;const outdated=d.sourceRosterRevision!==team.revision;
 const names=new Map([...a.draft.players.map(p=>[p.player_id,p.display_name] as const),...team.players.map(m=>[m.player_id,m.player.name] as const)]);
 const ids=[...new Set([...Object.keys(d.players),...team.players.filter(p=>!p.player.archived).map(p=>p.player_id)])];
 function check(id:string,yes:boolean){const players={...d.players};if(yes)players[id]=team.players.find(p=>p.player_id===id)?.shirt_number??'';else delete players[id];draft.change({...d,players})}
 return <><Link className="breadcrumb" to={`/captain/teams/${a.team_id}/applications`}>← Турниры команды</Link><div className="page-head"><div><h1>{a.tournament.name}</h1><p className="muted">{a.team_name} · {applicationStatuses[a.status]}</p></div><span className="chip">{deadline(a.tournament)}</span></div>
  {a.reason&&<div className={a.status==='changes_requested'?'warning':'draft-banner'}>{a.reason}</div>}{closed(a.tournament)&&<p className="warning">Подача заявок закрыта. Сохранённая версия остаётся доступной.</p>}
  <div className="captain-application-columns"><section className="surface"><h2>Черновик заявки</h2><p className="muted">Номера относятся к этому турниру. Отправленная версия сохранится в истории.</p>{outdated&&<p className="warning">Постоянный состав изменился. Сравните его с черновиком перед отправкой.</p>}
   <button disabled={locked} onClick={()=>draft.change({sourceRosterRevision:team.revision??0,players:Object.fromEntries(team.players.filter(m=>!m.player.archived).map(m=>[m.player_id,m.shirt_number??'']))})}>Взять текущий состав</button>
   <fieldset className="team-fieldset" disabled={locked}>{ids.map(id=><div className="roster-row" key={id}><Check label={names.get(id)??'Игрок из прежней заявки'} checked={id in d.players} onChange={yes=>check(id,yes)}/>{id in d.players&&<Field label={`Номер ${names.get(id)??'игрока'}`}><input maxLength={10} value={d.players[id]} onChange={e=>draft.change({...d,players:{...d.players,[id]:e.target.value}})}/></Field>}</div>)}</fieldset>
   <p className="muted small">{dirty?'Сначала сохраните изменения черновика':`Игроков: ${Object.keys(d.players).length}`}</p><div className="row wrap"><button disabled={locked} onClick={()=>void command.execute(`/captain/applications/${a.id}/draft`,{expected_revision:a.revision,source_roster_revision:d.sourceRosterRevision,players:Object.entries(d.players).map(([player_id,shirt_number])=>({player_id,shirt_number:shirt_number||null}))},'PUT')}>{a.status==='accepted'?'Сохранить новый черновик':'Сохранить черновик заявки'}</button>
   <button className="primary" disabled={locked||dirty||outdated||closed(a.tournament)||a.status==='submitted'||a.status==='accepted'||!Object.keys(d.players).length} onClick={()=>void command.execute(`/captain/applications/${a.id}/submit`,{expected_revision:a.revision})}>Отправить заявку</button></div><CommandStatus command={command}/>{Boolean(command.error)&&<button onClick={onRefresh}>Сверить свежую версию, сохранив ввод</button>}
  </section><section className="surface"><h2>{a.submitted_version?`Отправленная версия №${a.submitted_version.number}`:'Заявка ещё не отправлена'}</h2>{a.submitted_version?<><p className="muted">{a.accepted_version_id===a.submitted_version.id?'Эта версия принята организатором':'Изменения черновика не меняют эту версию'}</p><ul className="captain-frozen-roster">{a.submitted_version.payload.players.map(p=><li key={p.player_id}><span>{p.display_name}</span><b>№ {p.shirt_number??'—'}</b></li>)}</ul></>:<p className="muted">После отправки здесь появится состав для рассмотрения.</p>}
   {(a.versions?.length??0)>1&&<details><summary>История заявок</summary>{a.versions!.map(v=><p key={v.id}>Версия №{v.number} · Игроков: {v.payload.players.length}{v.id===a.accepted_version_id?' · принята':''}</p>)}</details>}
  </section></div></>;
}
