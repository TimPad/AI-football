import {useState,type ChangeEvent} from 'react';
import {Link,useNavigate,useParams} from 'react-router-dom';
import {Upload,FileSpreadsheet,CheckCircle2,ArrowLeft} from 'lucide-react';
import {api,post,ApiError} from '../../api/client';
import {useLoad,Loading,ErrorBox} from '../../components/ui';
import {useAuth} from '../auth/Auth';
import {useDraft} from '../protocol/drafts';
import {ImportMapping} from './ImportMapping';
import {ImportPreview} from './ImportPreview';
import {initialConfig,type ImportView,type ImportConfig,type ImportResult} from './types';
import './roster-import.css';

type Draft={config:ImportConfig,pending:{request_id:string,expected_revision:number}|null};
const validDraft=(v:unknown):v is Draft=>!!v&&typeof v==='object'&&'config' in v&&'pending' in v;

export function RosterImportLaunch({scope,targetId,entryId,disabled=false,audience='admin'}:{scope:'team'|'tournament',targetId:string,entryId?:string,disabled?:boolean,audience?:'admin'|'captain'}){
 const base=audience==='captain'?'/captain/roster-imports':'/roster-imports';
 const navigate=useNavigate();const [busy,setBusy]=useState(false);const [error,setError]=useState<unknown>();
 async function upload(e:ChangeEvent<HTMLInputElement>){const file=e.target.files?.[0];if(!file)return;setBusy(true);setError(undefined);
  try{if(file.size>5*1024*1024)throw Error('Файл Excel больше 5 МиБ');const body=new FormData();body.set('scope',scope);body.set('target_id',targetId);body.set('file',file);if(entryId)body.set('entry_id',entryId);
   const result=await api<ImportView>(base,{method:'POST',body});navigate(`${base}/${result.id}`);
  }catch(error){setError(error)}finally{setBusy(false);e.target.value=''}
 }
 return <div className="import-launch"><label className={`button import-upload ${busy||disabled?'disabled':''}`}><Upload/>{busy?'Читаем Excel…':'Загрузить Excel'}
  <input aria-label="Файл Excel" type="file" accept=".xlsx" disabled={disabled||busy} onChange={upload}/></label>
  <a className="small" href={`/api/v1${base}/template?scope=${entryId?'team':scope}`} download><FileSpreadsheet/>Шаблон Excel</a><ErrorBox error={error}/>
 </div>;
}

export function RosterImportPage(){const {id=''}=useParams();const {session}=useAuth();
 const state=useLoad(()=>api<ImportView>(`/roster-imports/${id}`),id);
 return state.data?<RosterImportEditor key={id} value={state.data} actorId={session!.id} onLoaded={state.setData}/>:<Loading error={state.error} retry={state.reload}/>;
}

export function RosterImportEditor({value,actorId,onLoaded,audience='admin'}:{value:ImportView,actorId:string,onLoaded:(v:ImportView)=>void,audience?:'admin'|'captain'}){
 const base=audience==='captain'?'/captain/roster-imports':'/roster-imports';
 const draft=useDraft<Draft>(`aifootball:import:${audience==='captain'?'captain:':''}${actorId}:${value.id}`,{config:initialConfig(value),pending:null},validDraft);
 const d=draft.value;const [busy,setBusy]=useState(false);const [error,setError]=useState<unknown>();
 const back=value.scope==='team'?`${audience==='captain'?'/captain':''}/teams/${value.target_id}`:value.entry_id?`/tournaments/${value.target_id}/teams/${value.entry_id}`:`/tournaments/${value.target_id}?tab=teams`;
 const dirty=JSON.stringify(d.config)!==JSON.stringify(initialConfig(value));
 const locked=busy||!!d.pending||draft.corrupt;
 const change=(config:ImportConfig)=>draft.change({config,pending:null});
 async function check(){setError(undefined);setBusy(true);try{const updated=await api<ImportView>(`${base}/${value.id}/preview`,{method:'PUT',body:JSON.stringify({...d.config,expected_revision:value.revision})});onLoaded(updated);draft.markSaved(d)}catch(e){setError(e)}finally{setBusy(false)}}
 async function apply(){setError(undefined);setBusy(true);const body=d.pending??{request_id:crypto.randomUUID(),expected_revision:value.revision};draft.change({...d,pending:body});
  try{const result=await post<ImportResult>(`${base}/${value.id}/commit`,body);draft.clear();onLoaded({...value,status:'committed',can_commit:false,result})}
  catch(e){setError(e);if(e instanceof ApiError&&e.status>0&&e.status<500)draft.change({...d,pending:null})}finally{setBusy(false)}
 }
 async function refresh(){setBusy(true);try{onLoaded(await api<ImportView>(`${base}/${value.id}`));setError(undefined)}catch(e){setError(e)}finally{setBusy(false)}}
 if(value.status==='committed'&&value.result){const r=value.result;return <div className="import-page"><Link className="breadcrumb" to={back}><ArrowLeft/>К составу</Link>
  <section className="surface import-result"><CheckCircle2/><h1>Состав загружен</h1><p>Новых игроков: {r.players_created} · существующих: {r.players_reused} · команд: {r.teams_created} · пропущено строк: {r.skipped_rows}</p>
   <div className="import-result-links">{r.links.map(link=><Link key={link.path} to={link.path}>{link.label} →</Link>)}</div><Link className="button primary" to={back}>Вернуться к управлению</Link>
  </section></div>}
 return <div className="import-page"><Link className="breadcrumb" to={back}><ArrowLeft/>Вернуться к составу</Link><div className="page-head"><div><h1>Проверка состава</h1>
  <p className="muted">{value.scope==='team'?'Постоянный состав команды':'Заявка этого турнира'} · Игроки добавятся к существующим. Другие заявки и матчи сохраняются.</p></div></div>
  <div className="import-progress" aria-label="Этапы импорта"><span className="done">1. Excel загружен</span><span className="active">2. Проверьте состав</span><span>3. Примените изменения</span></div>
  <ImportMapping value={value} config={d.config} onChange={change} disabled={locked}/>
  {value.rows.length>0&&<ImportPreview value={value} config={d.config} onChange={change} disabled={locked}/>}
  <ErrorBox error={error}/>{draft.error&&<ErrorBox error={draft.error}/>}
  {error instanceof ApiError&&error.status===409&&<button type="button" disabled={busy} onClick={refresh}>Обновить предпросмотр, сохранив ввод</button>}
  {d.pending&&<p className="warning">Ответ на применение не получен. Повторите тот же запрос — игроки не создадутся повторно.</p>}
  <div className="import-save-bar"><div><b>{value.summary.players_created??0} новых игроков · {value.summary.players_reused??0} существующих</b>
   <p className="muted small">{dirty?'Проверьте изменения перед применением':value.summary.errors?`Строк с ошибками: ${value.summary.errors}`:value.rows.length?'Строки проверены. Можно применять.':'Сопоставьте столбцы и проверьте строки'}</p></div>
   <div className="row wrap"><a href={`/api/v1${base}/${value.id}/report`} download>Отчёт проверки</a><button type="button" disabled={locked} onClick={check}>{value.rows.length?'Проверить изменения':'Проверить строки'}</button>
    <button type="button" className="primary" disabled={busy||draft.corrupt||(!d.pending&&(!value.can_commit||dirty))} onClick={apply}>{busy?'Сохраняем…':d.pending?'Повторить применение':'Применить импорт'}</button></div>
  </div>
 </div>;
}
