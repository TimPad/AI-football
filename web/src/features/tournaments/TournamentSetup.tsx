import {useState,type FormEvent} from 'react';
import {Link,useNavigate,useParams,useSearchParams} from 'react-router-dom';
import {api,all,post,ApiError} from '../../api/client';
import type {Tournament,Entry,RegVersion,Match} from '../../api/domain';
import {Field,ErrorBox,useLoad,Loading} from '../../components/ui';
import {useAuth} from '../auth/Auth';
import {useDraft} from '../protocol/drafts';
import {Rules,Entries} from './TournamentPage';
import './setup.css';

type Draft={request_id:string,name:string,season:string,starts_on:string,ends_on:string,timezone:string,mode:'quick'|'full'|null};
function valid(v:unknown):v is Draft{if(!v||typeof v!=='object')return false;const d=v as Draft;return ['request_id','name','season','starts_on','ends_on','timezone'].every(k=>typeof d[k as keyof Draft]==='string')&&(d.mode===null||d.mode==='quick'||d.mode==='full')}
export function TournamentCreate(){
 const {session}=useAuth();const navigate=useNavigate();const [initial]=useState<Draft>(()=>({request_id:crypto.randomUUID(),name:'',season:`${new Date().getFullYear()}`,starts_on:'',ends_on:'',timezone:'Europe/Moscow',mode:null}));
 const draft=useDraft(`aifootball:tournament:new:${session!.id}`,initial,valid);const d=draft.value;
 const [busy,setBusy]=useState(false);const [error,setError]=useState<unknown>();
 const update=(key:keyof Draft,value:string)=>draft.change({...d,[key]:value,request_id:crypto.randomUUID()});
 async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const mode=d.mode??((e.nativeEvent as SubmitEvent).submitter?.getAttribute('data-mode')==='full'?'full':'quick');
  const pending={...d,mode};draft.change(pending);setBusy(true);setError(undefined);
  try{const {mode:_,...body}=pending;void _;const t=await post<Tournament>('/tournaments',{...body,visibility:'draft'});draft.clear();navigate(mode==='full'?`/tournaments/${t.id}/setup?step=rules`:`/tournaments/${t.id}`)}
  catch(e){setError(e);if(e instanceof ApiError&&e.status>0&&e.status<500)draft.change({...pending,mode:null})}finally{setBusy(false)}
 }
 return <div className="setup-page"><Link className="breadcrumb" to="/tournaments">← Турниры</Link><h1>Новый турнир</h1><p className="muted">Сначала сведения. Команды и регламент можно добавить сейчас или позже.</p>
  <form onSubmit={submit}><fieldset className="team-fieldset" disabled={busy||!!d.mode||draft.corrupt}><section className="surface form-grid">
   <Field label="Название турнира"><input required maxLength={200} value={d.name} onChange={e=>update('name',e.target.value)} autoFocus/></Field>
   <Field label="Сезон"><input required maxLength={100} value={d.season} onChange={e=>update('season',e.target.value)}/></Field>
   <Field label="Начало турнира"><input required type="date" value={d.starts_on} onChange={e=>update('starts_on',e.target.value)}/></Field>
   <Field label="Окончание турнира"><input required type="date" min={d.starts_on} value={d.ends_on} onChange={e=>update('ends_on',e.target.value)}/></Field>
   <Field label="Часовой пояс"><input required value={d.timezone} onChange={e=>update('timezone',e.target.value)} list="setup-timezones"/><datalist id="setup-timezones"><option>Europe/Moscow</option><option>Asia/Yekaterinburg</option><option>Asia/Novosibirsk</option><option>Europe/Kaliningrad</option></datalist></Field>
  </section></fieldset><ErrorBox error={error}/><ErrorBox error={draft.error}/>{d.mode&&!busy&&<p className="warning">Ответ не получен. Повторите создание с сохранёнными данными.</p>}
  <div className="setup-actions">{d.mode?<button className="primary" disabled={busy} type="submit">{busy?'Создаём…':'Повторить создание'}</button>:<><button type="submit" disabled={busy||draft.corrupt} data-mode="quick">Создать турнир</button><button type="submit" disabled={busy||draft.corrupt} className="primary" data-mode="full">Создать и добавить команды</button></>}
   <span className="muted small">Турнир появится на сайте после отдельной публикации.</span></div>
  </form></div>;
}

const STEPS=[['rules','1. Регламент'],['teams','2. Команды и игроки'],['review','3. Проверка']];
export function TournamentSetup(){const {id=''}=useParams();const [params,setParams]=useSearchParams();const step=STEPS.some(([key])=>key===params.get('step'))?params.get('step')!:'rules';
 const state=useLoad(async()=>{const [t,entries,rules,matches]=await Promise.all([api<Tournament>(`/tournaments/${id}`),all<Entry>(`/tournaments/${id}/entries`),all<RegVersion>(`/tournaments/${id}/regulations`),all<Match>(`/tournaments/${id}/matches`)]);return {t,entries,rules,matches}},id);
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const d=state.data;const index=STEPS.findIndex(([key])=>key===step);
 return <div className="setup-page"><Link className="breadcrumb" to={`/tournaments/${id}`}>← {d.t.name}</Link><div className="page-head"><div><h1>Настройка турнира</h1><p className="muted">{d.t.name} · Черновик сохранён на сервере</p></div><Link className="button" to={`/tournaments/${id}`}>Сохранить и выйти</Link></div>
  <nav className="setup-steps" aria-label="Шаги настройки">{STEPS.map(([key,label])=><Link key={key} aria-current={key===step?'step':undefined} to={`?step=${key}`}>{label}</Link>)}</nav>
  {step==='rules'&&<Rules key={d.rules.map(r=>r.id).join()} tid={id} data={d} onSaved={state.reload}/>}
  {step==='teams'&&<Entries tid={id} data={d} onSaved={state.reload}/>}
  {step==='review'&&<section className="surface"><h2>Готовность турнира</h2><p>{d.rules.length?'✓ Регламент сохранён':'Добавьте регламент'}</p><p>{d.entries.length>=2?'✓ Команды добавлены':`Команд: ${d.entries.length}. Для первого матча нужны две.`}</p><p>Страница турнира: {d.t.visibility==='public'?'опубликована':'черновик'}</p>
   <Link className="button primary" to={`/tournaments/${id}`}>Перейти к матчам</Link><p className="muted">В кабинете можно составить расписание и отдельно опубликовать страницу турнира.</p></section>}
  <div className="setup-actions">{index>0&&<button onClick={()=>setParams({step:STEPS[index-1][0]})}>Назад</button>}{index<2&&<button className="primary" disabled={step==='rules'&&!d.rules.length} onClick={()=>setParams({step:STEPS[index+1][0]})}>Продолжить</button>}</div>
 </div>;
}
