import {useEffect,useRef,useState,type FormEvent} from 'react';
import {AlertTriangle,Check as CheckIcon} from 'lucide-react';
import {post} from '../../api/client';
import type {Entry,RegVersion} from '../../api/domain';
import {Check,ErrorBox,Field,Modal} from '../../components/ui';
import type {Standings,Template} from './api';
import type {components} from '../../api/types';
import {FormatHelp} from './FormatHelp';
import {ParticipantsPicker,storeParticipants,storedParticipants} from './ParticipantsPicker';
import {Stepper} from './Stepper';
import {TEMPLATE_HINT,TEMPLATE_NAME,plural} from './labels';
import './stages.css';

type Card=components['schemas']['EstimateCard'];
type Params={group_count:number;per_group:number;best_thirds:number;legs:1|2;third_place:boolean;grand_final_reset:boolean;rounds:number;with_playoff:boolean;playoff_teams:number};
const TEMPLATES:Template[]=['league','groups_playoff','playoff','double_elim','swiss'];
const DEFAULTS:Params={group_count:2,per_group:2,best_thirds:0,legs:1,third_place:false,grand_final_reset:false,rounds:4,with_playoff:false,playoff_teams:4};

// Параметры шаблона для расчёта и сохранения: только те, что относятся к выбранному формату.
function paramsFor(template:Template,p:Params){
 if(template==='groups_playoff')return {group_count:p.group_count,per_group:p.per_group,best_thirds:p.best_thirds,legs:p.legs,third_place:p.third_place};
 if(template==='league')return {legs:p.legs,...(p.with_playoff?{playoff_teams:p.playoff_teams,third_place:p.third_place}:{})};
 if(template==='swiss')return {rounds:p.rounds,...(p.with_playoff?{playoff_teams:p.playoff_teams,third_place:p.third_place}:{})};
 if(template==='playoff')return {third_place:p.third_place};
 return {grand_final_reset:p.grand_final_reset};
}
const facts=(c:Card)=>[`${c.matches} ${plural(c.matches,'матч','матча','матчей')}`,
 c.per_team[0]===c.per_team[1]?`${c.per_team[0]} на команду`:`${c.per_team[0]}–${c.per_team[1]} на команду`,`${c.days} ${plural(c.days,'игровой день','игровых дня','игровых дней')}`];

export function FormatStep({tid,regulations,standings,entries,onSaved}:{tid:string;regulations:RegVersion[];standings:Standings;entries:Entry[];onSaved:()=>void}){
 const locked=standings.stages.some(s=>s.draw);
 const [template,setTemplate]=useState<Template>('groups_playoff');
 const [p,setP]=useState<Params>(DEFAULTS);const touched=useRef(false);
 const [days,setDays]=useState<number|null>(null);const [perDay,setPerDay]=useState<number|null>(null);
 const [participants,setParticipants]=useState(()=>storedParticipants(tid,entries));const [picking,setPicking]=useState(false);
 const [cards,setCards]=useState<Card[]>([]);const [estimateError,setEstimateError]=useState(false);const [retry,setRetry]=useState(0);
 const [regulation,setRegulation]=useState(regulations[0]?.id??'');const [playoffRegulation,setPlayoffRegulation]=useState('');
 const [requestId,setRequestId]=useState(()=>crypto.randomUUID());const [busy,setBusy]=useState(false);const [error,setError]=useState<unknown>();
 const teams=participants.length;
 const change=(next:Partial<Params>)=>{touched.current=true;setP(old=>({...old,...next}));setRequestId(crypto.randomUUID())};
 const choose=(t:Template)=>{setTemplate(t);setRequestId(crypto.randomUUID())};
 // Расчёт с задержкой 300 мс; прошлые карточки остаются на экране, пока не придёт новый ответ.
 useEffect(()=>{
  if(teams<2)return;
  const controller=new AbortController();
  const timer=setTimeout(async()=>{
   try{const r=await post<{cards:Card[]}>(`/tournaments/${tid}/format/estimate`,{teams,days,per_day:perDay,template,params:touched.current?paramsFor(template,p):{}});
    if(controller.signal.aborted)return;setCards(r.cards);setEstimateError(false);
    if(!touched.current){const auto=r.cards.find(c=>c.template===template)?.params as Partial<Params>|undefined;if(auto)setP(old=>({...old,...auto}))}}
   catch{if(!controller.signal.aborted)setEstimateError(true)}
  },300);
  return()=>{controller.abort();clearTimeout(timer)};
 },[tid,teams,days,perDay,template,JSON.stringify(paramsFor(template,p)),retry]);
 async function submit(e:FormEvent){e.preventDefault();setBusy(true);setError(undefined);
  const params=paramsFor(template,p) as Record<string,unknown>;
  try{await post(`/tournaments/${tid}/format`,{request_id:requestId,template,regulation_id:regulation,playoff_regulation_id:playoffRegulation||null,...params});storeParticipants(tid,participants);onSaved()}
  catch(e){setError(e)}finally{setBusy(false)}}
 const card=(t:Template)=>cards.find(c=>c.template===t);
 const selected=card(template);
 const withPlayoff=template==='groups_playoff'||((template==='league'||template==='swiss')&&p.with_playoff);
 return <form className="surface format-step" onSubmit={submit}>
  <div className="page-head"><h2>Формат турнира</h2><FormatHelp/></div>
  {locked&&<p className="muted">Формат закреплён жеребьёвкой.</p>}
  <div className="format-inputs">
   <div className="team-count"><span>Команд: <b>{teams}</b></span><button type="button" className="quiet" disabled={locked} onClick={()=>setPicking(true)}>Изменить</button></div>
   <Stepper label="Игровых дней" value={days} min={1} max={365} optional onChange={setDays}/>
   <Stepper label="Матчей за день" value={perDay} min={1} max={50} optional onChange={setPerDay}/>
  </div>
  {estimateError&&<p className="warning" role="status">Не удалось пересчитать. <button type="button" className="quiet" onClick={()=>setRetry(n=>n+1)}>Повторить</button></p>}
  <div className="format-cards" role="radiogroup" aria-label="Формат">{TEMPLATES.map(t=>{const c=card(t);return <button key={t} type="button" role="radio" className="format-card" aria-checked={template===t}
   aria-disabled={locked} disabled={locked} onClick={()=>choose(t)}>
   <span className="format-card-head"><strong>{TEMPLATE_NAME[t]}</strong>{c?.recommended&&<span className="badge">Рекомендуем</span>}</span>
   <span>{TEMPLATE_HINT[t]}</span>
   {c&&<span className="format-facts">{facts(c).join(' · ')}</span>}
   {c?.fits===false&&<span className="format-misfit">Не уложится в {days} {plural(days??0,'день','дня','дней')}</span>}
   {c?.recommended&&c.reason&&<span className="format-reason"><CheckIcon aria-hidden="true"/>{c.reason}</span>}
  </button>})}</div>
  {selected&&(selected.warnings.length>0||selected.fix)&&<div className="format-warnings" role="status">{selected.warnings.map(w=><p key={w} className="warning"><AlertTriangle aria-hidden="true"/>{w}</p>)}
   {selected.fix&&'group_count' in selected.fix&&<button type="button" onClick={()=>change({group_count:Number(selected.fix!.group_count)})}>Сделать {String(selected.fix.group_count)} {plural(Number(selected.fix.group_count),'группу','группы','групп')}</button>}</div>}
  <fieldset className="team-fieldset" disabled={locked||busy}><div className="form-grid format-params">
   {template==='groups_playoff'&&<><Stepper label="Групп" value={p.group_count} min={2} max={16} onChange={v=>change({group_count:v??2})}/>
    <Stepper label="Выходят из группы" value={p.per_group} min={1} max={16} onChange={v=>change({per_group:v??1})}/>
    <Stepper label={`Лучшие ${p.per_group+1}-и места`} value={p.best_thirds} min={0} max={16} onChange={v=>change({best_thirds:v??0})}/></>}
   {(template==='league'||template==='groups_playoff')&&<div className="segmented" role="group" aria-label="Круги">{([1,2] as const).map(n=><button key={n} type="button" className={p.legs===n?'active':''} aria-pressed={p.legs===n} onClick={()=>change({legs:n})}>{n===1?'Один круг':'Два круга'}</button>)}</div>}
   {template==='swiss'&&<Stepper label="Туров" value={p.rounds} min={1} max={15} onChange={v=>change({rounds:v??1})}/>}
   {(template==='league'||template==='swiss')&&<><Check label="Добавить плей-офф" checked={p.with_playoff} onChange={v=>change({with_playoff:v})}/>
    {p.with_playoff&&<Stepper label="В плей-офф выходят" value={p.playoff_teams} min={2} max={64} onChange={v=>change({playoff_teams:v??2})}/>}</>}
   {(withPlayoff||template==='playoff')&&<Check label="Матч за 3-е место" checked={p.third_place} onChange={v=>change({third_place:v})}/>}
   {template==='double_elim'&&<Check label="Переигровка финала, если победит команда из нижней сетки" checked={p.grand_final_reset} onChange={v=>change({grand_final_reset:v})}/>}
   <Field label="Регламент матчей"><select required value={regulation} onChange={e=>{setRegulation(e.target.value);setRequestId(crypto.randomUUID())}}>{regulations.map(r=><option key={r.id} value={r.id}>{r.variant_name} · версия {r.version}</option>)}</select></Field>
   {withPlayoff&&<Field label="Регламент плей-офф"><select value={playoffRegulation} onChange={e=>{setPlayoffRegulation(e.target.value);setRequestId(crypto.randomUUID())}}>
    <option value="">Тот же</option>{regulations.map(r=><option key={r.id} value={r.id}>{r.variant_name} · версия {r.version}</option>)}</select></Field>}
  </div>{selected&&<p className="format-summary">{selected.summary}</p>}</fieldset>
  <ErrorBox error={error}/>
  {!locked&&<div className="setup-actions"><button className="primary" disabled={busy||!regulation||teams<2}>{busy?'Сохраняем…':standings.stages.length?'Заменить формат':'Сохранить формат'}</button>
   {standings.stages.length>0&&<span className="muted small">Сейчас: {standings.stages.map(s=>s.name).join(' → ')}</span>}</div>}
  {picking&&<Modal title="Кто играет" sheet onClose={()=>setPicking(false)}><ParticipantsPicker entries={entries} value={participants} onChange={setParticipants}/>
   <button type="button" className="primary" disabled={participants.length<2} onClick={()=>{storeParticipants(tid,participants);setPicking(false)}}>Готово</button></Modal>}
 </form>;
}
