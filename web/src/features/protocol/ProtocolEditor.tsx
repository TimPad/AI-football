import {useState} from 'react';
import {Plus} from 'lucide-react';
import type {MatchEvent} from '../../api/domain';
import {kinds} from '../../api/domain';
import {useAuth} from '../auth/Auth';
import {ErrorBox,Loading,Modal,downloadJson} from '../../components/ui';
import {ClockPanel} from './ClockPanel';
import {EventForm,isEventDraft,newEventDraft,type EventDraft} from './EventForm';
import {EventJournal} from './EventJournal';
import {TotalsForm,Completeness,NotesPanel,VersionsPanel} from './ProtocolPanels';
import {Attachments} from './Attachments';
import {useDraft} from './drafts';
import {SessionChrome,useProtocolSession,useSessionDispatch} from './ProtocolSession';
import {ModeSelector,useProtocolMode} from './ProtocolMode';

export function ProtocolEditor(){
 const state=useProtocolSession();
 return state.queue?<ProtocolEditorBody/>:<Loading error={state.error}/>;
}
function ProtocolEditorBody(){
 const {session}=useAuth();const state=useProtocolSession();const {dispatch,error,setError}=useSessionDispatch();
 const queue=state.queue!;const m=queue.view;const id=m.id;
 const [open,setOpen]=useState(false);const [removing,setRemoving]=useState<string|null>(null);
 const draft=useDraft<EventDraft|null>(`aifootball:event:v1:${session!.id}:${id}`,null,isEventDraft);
 const mode=useProtocolMode(id);
 // Подтверждённый протокол открывается итогом версии; режимы ввода нужны только при правке.
 const confirmed=!m.protocol.draft;
 function add(kind:MatchEvent['kind']){draft.change(newEventDraft(kind));setOpen(true)}
 function edit(eventId:string){let e=m.protocol.events.find(e=>e.id===eventId)!;const link='penalty_id' in e&&e.penalty_id?e.penalty_id:e.kind==='penalty_awarded'?e.id:null;if(link){const attempt=m.protocol.events.find(e=>e.kind==='penalty_attempt'&&e.penalty_id===link);if(attempt)e=attempt}draft.change(newEventDraft(e.kind,e));setOpen(true)}
 const target=m.protocol.events.find(e=>e.id===removing);const link=target&&('penalty_id' in target&&target.penalty_id?target.penalty_id:target.kind==='penalty_awarded'?target.id:null);const removed=target?(link?m.protocol.events.filter(e=>e.id===link||('penalty_id' in e&&e.penalty_id===link)):[target]):[];
 return <SessionChrome extra={{event:draft.value,eventRaw:draft.raw}}>{({disabled,readOnly})=><>
  <ErrorBox error={error||draft.error||mode.error}/>{draft.corrupt&&<button onClick={()=>{downloadJson(draft.raw,'повреждённый-ввод.json');draft.clear()}}>Скачать и очистить повреждённый ввод</button>}
  <section className="surface score-band"><div className="score-teams"><div>{m.home.team.name}</div><div className="big-score">{m.projection.effective_score.home??'—'} <span>:</span> {m.projection.effective_score.away??'—'}<small>Известные голы: {m.projection.event_score.home} : {m.projection.event_score.away}</small></div><div>{m.away.team.name}</div></div>{mode.value!=='result'&&<ClockPanel match={m} dispatch={dispatch} disabled={readOnly}/>}</section>
  {confirmed&&<VersionsPanel match={m} dispatch={dispatch} disabled={disabled}/>}
  {!confirmed&&<ModeSelector value={mode.value} onChange={mode.change}/>}
  {mode.value==='result'?<div className="protocol-layout result-mode"><section className="surface protocol-side"><TotalsForm match={m} dispatch={dispatch} disabled={readOnly}/></section>
   <aside className="surface protocol-side"><p className="muted">Полнота разделов не меняется автоматически: отметьте только то, что проверено.</p><Completeness match={m} dispatch={dispatch} disabled={readOnly}/></aside></div>
  :<>{draft.value&&!open&&<div className="draft-banner">Есть сохранённый ввод события. <button onClick={()=>setOpen(true)}>Продолжить заполнение</button><button onClick={()=>{downloadJson(draft.value);draft.clear()}}>Скачать и убрать</button></div>}
  <div className="protocol-layout"><section className="surface event-panel"><div className="panel-head"><h2>События матча</h2></div>{!confirmed&&<div className="event-toolbar">{(['goal','foul','card','timeout'] as const).map((kind,i)=><button className={i===0?'primary':''} disabled={readOnly} key={kind} onClick={()=>add(kind)}><Plus/>{kinds[kind]}</button>)}<select aria-label="Другие события" disabled={readOnly} value="" onChange={e=>{if(e.target.value)add(e.target.value as MatchEvent['kind'])}}><option value="">Ещё события…</option>{(['penalty_awarded','penalty_attempt','shootout_attempt','substitution','stoppage','period_start','period_end'] as const).map(kind=><option key={kind} value={kind}>{kinds[kind]}</option>)}</select></div>}<EventJournal events={m.protocol.events} lineup={m.lineup} home={m.home.team.name} away={m.away.team.name} disabled={readOnly} onEdit={edit} onRemove={setRemoving}/><div className="journal-foot">{m.protocol.events.length} событий · время вводится вручную</div>{m.projection.warnings.map(w=><p className="warning" key={w}>{w}</p>)}</section><aside className="surface protocol-side"><TotalsForm match={m} dispatch={dispatch} disabled={readOnly}/><hr/><Completeness match={m} dispatch={dispatch} disabled={readOnly}/></aside></div>
  <details className="protocol-extras" key={`extras:${confirmed}`} open={!confirmed}><summary>Примечания и документы{m.protocol.notes||m.protocol.public_notes?' · есть записи':''}</summary>
   <NotesPanel key={m.id} match={m} dispatch={dispatch} disabled={readOnly}/><Attachments match={m} dispatch={dispatch} disabled={disabled} refresh={()=>queue.refresh()}/></details></>}
  {!confirmed&&<VersionsPanel match={m} dispatch={dispatch} disabled={disabled}/>}
  {open&&draft.value&&<Modal title={`${draft.value.editId?'Редактировать: ':'Новое событие: '}${kinds[draft.value.kind]}`} onClose={()=>setOpen(false)}><EventForm match={m} draft={draft.value} onChange={draft.change} disabled={readOnly} onSaved={async d=>{await dispatch(d);draft.clear();setOpen(false)}}/></Modal>}
  {target&&<Modal title="Отменить событие" onClose={()=>setRemoving(null)}><p>В истории останется запись об отмене. Будут отменены следующие события:</p><ul>{removed.map(e=><li key={e.id}>{kinds[e.kind]}</li>)}</ul><button disabled={readOnly} onClick={async()=>{try{await dispatch({kind:'remove_event',payload:{event_id:target.id,related_ids:removed.filter(e=>e.id!==target.id).map(e=>e.id)}});setRemoving(null)}catch(e){setError(e)}}}>Отменить выбранные события</button><ErrorBox error={error}/></Modal>}
 </>}</SessionChrome>;
}
