import {useState,type FormEvent} from 'react';
import {Link,useNavigate,useParams,useSearchParams} from 'react-router-dom';
import {api,all,post,ApiError} from '../../api/client';
import type {Tournament,Entry,RegVersion,Match} from '../../api/domain';
import {Field,ErrorBox,useLoad,Loading} from '../../components/ui';
import {useAuth} from '../auth/Auth';
import {useDraft} from '../protocol/drafts';
import {Rules,Entries} from './TournamentPage';
import {TimezoneSelect,seasonOf} from './TournamentList';
import {useDocumentTitle} from '../../components/useDocumentTitle';
import {FormatStep} from '../stages/FormatStep';
import {StageWorkspace} from '../stages/StageWorkspace';
import type {Standings} from '../stages/api';
import './setup.css';

type Draft={request_id:string,name:string,season:string,starts_on:string,ends_on:string,timezone:string,mode:'quick'|'full'|null};
function valid(v:unknown):v is Draft{if(!v||typeof v!=='object')return false;const d=v as Draft;return ['request_id','name','season','starts_on','ends_on','timezone'].every(k=>typeof d[k as keyof Draft]==='string')&&(d.mode===null||d.mode==='quick'||d.mode==='full')}
export function TournamentCreate(){
 useDocumentTitle('Новый турнир');const {session}=useAuth();const navigate=useNavigate();const [initial]=useState<Draft>(()=>({request_id:crypto.randomUUID(),name:'',season:'',starts_on:'',ends_on:'',timezone:'Europe/Moscow',mode:null}));
 const draft=useDraft(`aifootball:tournament:new:${session!.id}`,initial,valid);const d=draft.value;
 const [busy,setBusy]=useState(false);const [error,setError]=useState<unknown>();
 const update=(key:keyof Draft,value:string)=>draft.change({...d,[key]:value,request_id:crypto.randomUUID()});
 // Одна кнопка «Далее»: черновик турнира создаётся и мастер переходит к регламенту.
 async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const mode=d.mode??'full';
  const pending={...d,season:seasonOf(d.starts_on,d.ends_on),mode};draft.change(pending);setBusy(true);setError(undefined);
  try{const {mode:_,...body}=pending;void _;const t=await post<Tournament>('/tournaments',{...body,visibility:'draft'});draft.clear();navigate(mode==='full'?`/tournaments/${t.id}/setup?step=rules`:`/tournaments/${t.id}`)}
  catch(e){setError(e);if(e instanceof ApiError&&e.status>0&&e.status<500)draft.change({...pending,mode:null})}finally{setBusy(false)}
 }
 const season=seasonOf(d.starts_on,d.ends_on);
 return <div className="setup-page"><Link className="breadcrumb" to="/tournaments">← Турниры</Link><h1>Новый турнир</h1><p className="muted">Сначала сведения. Команды и регламент — следующими шагами, их можно отложить.</p>
  <nav className="setup-steps" aria-label="Шаги настройки">{STEPS.map(([key,label])=>key==='info'?<span key={key} aria-current="step">{label}</span>:<span key={key} className="step-later">{label}</span>)}</nav>
  <form onSubmit={submit}><fieldset className="team-fieldset" disabled={busy||!!d.mode||draft.corrupt}><section className="surface form-grid">
   <Field label="Название турнира"><input required maxLength={200} value={d.name} onChange={e=>update('name',e.target.value)} autoFocus/></Field>
   <Field label="Часовой пояс"><TimezoneSelect value={d.timezone} onChange={v=>update('timezone',v)}/></Field>
   <Field label="Начало турнира"><input required type="date" value={d.starts_on} onChange={e=>update('starts_on',e.target.value)}/></Field>
   <Field label="Окончание турнира"><input required type="date" min={d.starts_on} value={d.ends_on} onChange={e=>update('ends_on',e.target.value)}/></Field>
   {season&&<p className="muted small setup-season">Сезон {season}</p>}
  </section></fieldset><ErrorBox error={error}/><ErrorBox error={draft.error}/>{d.mode&&!busy&&<p className="warning">Ответ не получен. Повторите создание с сохранёнными данными.</p>}
  <div className="setup-actions">{d.mode?<button className="primary" disabled={busy} type="submit">{busy?'Создаём…':'Повторить создание'}</button>:<button type="submit" disabled={busy||draft.corrupt} className="primary">Далее</button>}
   <span className="muted small">Турнир появится на сайте после отдельной публикации.</span></div>
  </form></div>;
}

// Шаг «Сведения» — страница создания; дальше настройка уже созданного черновика.
const STEPS=[['info','1. Сведения'],['rules','2. Регламент'],['teams','3. Команды и игроки'],['format','4. Формат'],['draw','5. Жеребьёвка'],['review','6. Проверка']];
const SETUP=STEPS.slice(1);
export function TournamentSetup(){const {id=''}=useParams();const [params,setParams]=useSearchParams();const step=SETUP.some(([key])=>key===params.get('step'))?params.get('step')!:'rules';
 const state=useLoad(async()=>{const [t,entries,rules,matches]=await Promise.all([api<Tournament>(`/tournaments/${id}`),all<Entry>(`/tournaments/${id}/entries`),all<RegVersion>(`/tournaments/${id}/regulations`),all<Match>(`/tournaments/${id}/matches`)]);const stages=await api<Standings>(`/tournaments/${id}/stages`);return {t,entries,rules,matches,stages}},id);
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const d=state.data;const index=SETUP.findIndex(([key])=>key===step);
 return <div className="setup-page"><Link className="breadcrumb" to={`/tournaments/${id}`}>← {d.t.name}</Link><div className="page-head"><div><h1>Настройка турнира</h1><p className="muted">{d.t.name} · Черновик сохранён на сервере</p></div><Link className="button" to={`/tournaments/${id}`}>Сохранить и выйти</Link></div>
  <nav className="setup-steps" aria-label="Шаги настройки">{STEPS.map(([key,label])=>key==='info'?<Link key={key} to={`/tournaments/${id}?tab=info`}>{label}</Link>:<Link key={key} aria-current={key===step?'step':undefined} to={`?step=${key}`}>{label}</Link>)}</nav>
  {step==='rules'&&<Rules key={d.rules.map(r=>r.id).join()} tid={id} data={d} onSaved={state.reload}/>}
  {step==='teams'&&<Entries tid={id} data={d} onSaved={state.reload}/>}
  {step==='format'&&(d.rules.length?<FormatStep key={d.stages.stages.map(s=>s.id).join()} tid={id} regulations={d.rules} standings={d.stages} entries={d.entries} onSaved={state.reload}/>:<p className="warning">Сначала сохраните регламент.</p>)}
  {step==='draw'&&(d.stages.stages.length?<StageWorkspace tournament={d.t} entries={d.entries} regulations={d.rules}/>:<p className="muted">Сначала выберите формат турнира.</p>)}
  {step==='review'&&<section className="surface"><h2>Готовность турнира</h2><p>{d.rules.length?'✓ Регламент сохранён':'Добавьте регламент'}</p><p>{d.entries.length>=2?'✓ Команды добавлены':`Команд: ${d.entries.length}. Для первого матча нужны две.`}</p><p>{d.stages.stages.length?`✓ Формат: ${d.stages.stages.map(s=>s.name).join(' → ')}`:'Формат не выбран — матчи можно создавать вручную'}</p><p>{d.stages.stages.length&&d.stages.stages.every(s=>s.draw||s.status!=='draft')?'✓ Жеребьёвка проведена':d.stages.stages.length?'Жеребьёвка ещё не проведена':''}</p><p>Страница турнира: {d.t.visibility==='public'?'опубликована':'черновик'}</p>
   <Link className="button primary" to={`/tournaments/${id}`}>Перейти к матчам</Link><p className="muted">В кабинете можно составить расписание и отдельно опубликовать страницу турнира.</p></section>}
  <div className="setup-actions">{index>0&&<button onClick={()=>setParams({step:SETUP[index-1][0]})}>Назад</button>}{index<SETUP.length-1&&<button className="primary" disabled={step==='rules'&&!d.rules.length} onClick={()=>setParams({step:SETUP[index+1][0]})}>Далее</button>}</div>
 </div>;
}
