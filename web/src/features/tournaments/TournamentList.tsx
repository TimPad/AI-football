import {useState,type FormEvent} from 'react';import {Link,} from 'react-router-dom';import {ArrowUpRight} from 'lucide-react';
import {useDocumentTitle} from '../../components/useDocumentTitle';
import {dateRange} from '../matches/timezone';
import {all,post,api} from '../../api/client';import type {Tournament} from '../../api/domain';import {useLoad,Loading,Empty,Field,ErrorBox} from '../../components/ui';
// Сезон считается из дат: «2026» или «2026/2027» — отдельное поле не нужно.
export const seasonOf=(starts:string,ends:string)=>{const a=starts.slice(0,4),b=ends.slice(0,4);return !a?'':!b||a===b?a:`${a}/${b}`};
export const TIMEZONES:[string,string][]=[['Europe/Kaliningrad','Калининград (МСК−1)'],['Europe/Moscow','Москва (МСК)'],['Europe/Samara','Самара (МСК+1)'],['Asia/Yekaterinburg','Екатеринбург (МСК+2)'],
 ['Asia/Omsk','Омск (МСК+3)'],['Asia/Novosibirsk','Новосибирск (МСК+4)'],['Asia/Krasnoyarsk','Красноярск (МСК+4)'],['Asia/Irkutsk','Иркутск (МСК+5)'],['Asia/Yakutsk','Якутск (МСК+6)'],
 ['Asia/Vladivostok','Владивосток (МСК+7)'],['Asia/Magadan','Магадан (МСК+8)'],['Asia/Kamchatka','Камчатка (МСК+9)']];
export const timezoneName=(tz:string)=>TIMEZONES.find(([id])=>id===tz)?.[1]??tz;
export function TimezoneSelect({value,onChange,name}:{value?:string;onChange?:(v:string)=>void;name?:string}){
 const current=value??'Europe/Moscow';const known=TIMEZONES.some(([id])=>id===current);
 return <select name={name} required {...(onChange?{value:current,onChange:e=>onChange(e.target.value)}:{defaultValue:current})}>{!known&&<option value={current}>{current}</option>}{TIMEZONES.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select>;
}
export function TournamentFields({value}:{value?:Tournament}){return <div className="form-grid"><Field label="Название турнира"><input name="name" required maxLength={200} defaultValue={value?.name}/></Field><Field label="Часовой пояс"><TimezoneSelect name="timezone" value={value?.timezone}/></Field><Field label="Начало турнира"><input name="starts_on" type="date" required defaultValue={value?.starts_on}/></Field><Field label="Окончание турнира"><input name="ends_on" type="date" required defaultValue={value?.ends_on}/></Field></div>}
export function TournamentSettings({value,onSaved}:{value?:Tournament,onSaved:(t:Tournament)=>void}){
 const [error,setError]=useState<unknown>();const [busy,setBusy]=useState(false);
 async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const f=new FormData(e.currentTarget);const body={...Object.fromEntries(f),season:seasonOf(String(f.get('starts_on')),String(f.get('ends_on')))};setBusy(true);setError(undefined);try{const t=value?await api<Tournament>(`/tournaments/${value.id}`,{method:'PATCH',body:JSON.stringify({...body,expected_revision:value.revision})}):await post<Tournament>('/tournaments',body);onSaved(t)}catch(e){setError(e)}finally{setBusy(false)}}
 return <form onSubmit={submit}><fieldset className="team-fieldset" disabled={busy||value?.archived}><TournamentFields value={value}/><ErrorBox error={error}/><button className="primary" disabled={busy}>{value?'Сохранить настройки':'Создать турнир'}</button></fieldset></form>
}
export function TournamentList(){
 useDocumentTitle('Турниры');
 const state=useLoad(()=>all<Tournament>('/tournaments'),'tournaments');const [archive,setArchive]=useState(false);
 return <><div className="page-head"><div><h1>Турниры</h1><p className="muted">Все сезоны и матчи вашего организатора</p></div><Link className="button primary" to="/tournaments/new">Создать турнир</Link></div><div className="tabs"><button className={!archive?'active':''} onClick={()=>setArchive(false)}>Действующие</button><button className={archive?'active':''} onClick={()=>setArchive(true)}>Архив</button></div><section className="surface">{!state.data?<Loading error={state.error} retry={state.reload}/>:state.data.filter(t=>t.archived===archive).length===0?<Empty>{archive?'В архиве пока нет турниров':'Создайте первый турнир, затем настройте регламент и добавьте команды.'}</Empty>:<div className="table-scroll"><table><thead><tr><th>Турнир</th><th>Сезон</th><th>Даты</th><th/></tr></thead><tbody>{state.data.filter(t=>t.archived===archive).map(t=><tr key={t.id}><td><Link className="strong" to={`/tournaments/${t.id}`}>{t.name}</Link></td><td>{t.season}</td><td>{dateRange(t.starts_on,t.ends_on)}</td><td><Link aria-label={`Открыть ${t.name}`} to={`/tournaments/${t.id}`}><ArrowUpRight/></Link></td></tr>)}</tbody></table></div>}</section></>
}