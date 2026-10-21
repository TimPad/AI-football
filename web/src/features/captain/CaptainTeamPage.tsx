import {useState,type FormEvent} from 'react';
import {Link,useNavigate,useParams} from 'react-router-dom';
import {api,post} from '../../api/client';
import type {components} from '../../api/types';
import {useLoad,Loading,Empty,Field} from '../../components/ui';
import {TeamEditor} from '../catalog/TeamEditor';
import {RosterImportLaunch,RosterImportEditor} from '../roster-import/RosterImportPage';
import type {ImportView} from '../roster-import/types';
import {useCaptainAuth} from './CaptainAuth';
import {useRatingCommand,CommandStatus} from '../ratings/commands';
type CaptainTeam=components['schemas']['CaptainTeamView'];
export function CaptainHome(){const teams=useLoad(()=>api<{items:CaptainTeam[]}>('/captain/teams'),'captain-teams');return <><div className="page-head"><div><h1>Мои команды</h1><p className="muted">Составы, турнирные заявки и проверка игроков</p></div><Link className="button" to="/captain/identity-tasks">Проверка игроков</Link><Link className="button primary" to="/captain/teams/new">Создать команду</Link></div>{!teams.data?<Loading error={teams.error} retry={teams.reload}/>:!teams.data.items.length?<section className="surface"><Empty>Создайте команду или примите приглашение организатора. Совпадение названия не даёт доступ к чужой команде.</Empty></section>:<div className="captain-team-cards">{teams.data.items.map(t=><Link key={t.id} className="surface" to={`/captain/teams/${t.id}`}><h2>{t.name}</h2><p className="muted">Игроков: {t.players.length}</p><b>{t.players.length?'Открыть команду →':'Добавить игроков →'}</b></Link>)}</div>}</>}
export function CaptainTeamPage(){const {id}=useParams();return <TeamContent key={id??'new'} id={id}/>}
function TeamContent({id}:{id?:string}){const {session}=useCaptainAuth();const navigate=useNavigate();const state=useLoad(()=>id?api<CaptainTeam>(`/captain/teams/${id}`):Promise.resolve(null),id??'new');
 if(state.data===undefined)return <Loading error={state.error} retry={state.reload}/>;const team=state.data??undefined;
 return <><Link className="breadcrumb" to="/captain">← Мои команды</Link>{team&&<div className="captain-team-tools"><RosterImportLaunch scope="team" targetId={team.id} audience="captain" disabled={team.archived}/><Link className="button" to={`/captain/teams/${id}/applications`}>Турниры и заявки</Link><Link className="button" to="/captain/identity-tasks">Проверка игроков</Link></div>}
  <p className="muted">Капитан ведёт состав своей команды. Исправления общей карточки существующего игрока отправляются организатору как предложение.</p>
  {(team?.profile_proposals?.length??0)>0&&<section className="surface"><h2>Предложения по игрокам</h2><p className="muted">Отправлено организатору: {team!.profile_proposals!.filter(p=>p.status==='pending').length}. Сохранённые карточки изменятся после рассмотрения.</p></section>}
  <TeamEditor key={`${id??'new'}:${team?.revision??0}`} embedded actorId={session!.id} draftScope={`captain:${id??'new'}`} imagePrefix="/captain/images" hidePlayerPicker existing={team} players={team?.players.map(m=>m.player)??[]} onSubmit={async body=>{
   const {expected_revision,...create}=body;return id?api<CaptainTeam>(`/captain/teams/${id}`,{method:'PUT',body:JSON.stringify(body)}):post<CaptainTeam>('/captain/teams',create)
  }} onSaved={saved=>{if(!id)navigate(`/captain/teams/${saved.id}`,{replace:true});else state.reload()}}/>
  {id&&<PlayerRequest teamId={id} onSaved={state.reload}/>}
 </>;
}
export function CaptainRosterImportPage(){const {id=''}=useParams();const {session}=useCaptainAuth();const state=useLoad(()=>api<ImportView>(`/captain/roster-imports/${id}`),id);return state.data?<RosterImportEditor key={id} value={state.data} actorId={session!.id} onLoaded={state.setData} audience="captain"/>:<Loading error={state.error} retry={state.reload}/>}
function PlayerRequest({teamId,onSaved}:{teamId:string,onSaved:()=>void}){const {session}=useCaptainAuth();const [name,setName]=useState('');const [number,setNumber]=useState('');const command=useRatingCommand(`aifootball:captain-person-request:${session!.id}:${teamId}`,()=>{setName('');setNumber('');onSaved()});
 async function submit(e:FormEvent){e.preventDefault();await command.execute(`/captain/teams/${teamId}/profile-proposals`,{player_id:crypto.randomUUID(),revision:0,name,shirt_number:number||null})}
 return <details className="surface"><summary>Запросить добавление игрока у организатора</summary><p className="muted">Если игрок уже участвовал за другую команду или импорт требует обращения, организатор проверит карточку и добавит его в ваш состав.</p><form onSubmit={submit}><div className="form-grid"><Field label="ФИО для запроса"><input required maxLength={200} disabled={command.locked} value={name} onChange={e=>setName(e.target.value)}/></Field><Field label="Командный номер для запроса"><input maxLength={10} disabled={command.locked} value={number} onChange={e=>setNumber(e.target.value)}/></Field></div><button disabled={command.locked} type="submit">Отправить обращение</button></form><CommandStatus command={command}/></details>;
}
