import {useState} from 'react';
import {ApiError,post} from '../../api/client';
import type {Entry} from '../../api/domain';
import {ErrorBox,Modal} from '../../components/ui';
import type {DrawPreview,StageView} from './api';
import {plural} from './labels';

const LETTERS='ABCDEFGHIJKLMNOP';
type Change={op:'remove'|'add'|'move';entry_id:string;group_no?:number;label:string};

// Состав этапа до первого результата: убрать, добавить, перенести. Каждое действие — с предпросмотром последствий.
export function RosterPanel({stage,entries,onSaved}:{stage:StageView;entries:Entry[];onSaved:()=>void}){
 const names=Object.fromEntries(entries.map(e=>[e.id,e.team.name]));
 const groups=stage.kind==='groups'?(stage.draw?.placement as string[][]):null;
 const members=groups?groups.flat():((stage.draw?.participants as string[]|null)??[]);
 const outside=entries.filter(e=>!members.includes(e.id));
 const [pending,setPending]=useState<{change:Change;preview:DrawPreview}|null>(null);
 const [adding,setAdding]=useState('');const [target,setTarget]=useState('');
 const [error,setError]=useState<unknown>();const [busy,setBusy]=useState(false);const [requestId,setRequestId]=useState(()=>crypto.randomUUID());
 const body=(c:Change)=>({op:c.op,entry_id:c.entry_id,group_no:c.group_no??null,expected_revision:stage.revision});
 async function ask(change:Change){setError(undefined);setBusy(true);
  try{setPending({change,preview:await post<DrawPreview>(`/stages/${stage.id}/draw/adjust/preview`,body(change))});setRequestId(crypto.randomUUID())}
  catch(e){setError(e instanceof ApiError&&e.code==='no_free_slot'?'Свободных мест нет. Проведите жеребьёвку заново':e)}finally{setBusy(false)}}
 async function apply(){if(!pending)return;setBusy(true);setError(undefined);
  try{await post(`/stages/${stage.id}/draw/adjust`,{...body(pending.change),request_id:requestId});setPending(null);onSaved()}catch(e){setError(e)}finally{setBusy(false)}}
 const row=(id:string,g?:number)=><li key={id} className="roster-row"><span>{names[id]}</span>
  {groups&&<select aria-label={`Перенести ${names[id]} в группу`} value="" onChange={e=>e.target.value&&ask({op:'move',entry_id:id,group_no:Number(e.target.value),label:`Перенести ${names[id]} в группу ${LETTERS[Number(e.target.value)-1]}`})}>
   <option value="">Перенести…</option>{groups.map((_,i)=>i+1!==g&&<option key={i} value={i+1}>В группу {LETTERS[i]}</option>)}</select>}
  <button type="button" className="quiet" onClick={()=>ask({op:'remove',entry_id:id,label:`Убрать ${names[id]} из этапа`})}>Убрать</button></li>;
 return <section className="roster-panel" aria-label="Состав этапа">
  <h3>Состав этапа</h3><p className="muted small">До первого результата состав можно менять. Пары пересчитываются только там, где изменился состав.</p>
  {groups?groups.map((g,i)=><div key={i}><h4>Группа {LETTERS[i]}</h4><ul className="roster-list">{g.map(id=>row(id,i+1))}</ul></div>)
   :<ul className="roster-list">{members.map(id=>row(id))}</ul>}
  {outside.length>0&&<div className="roster-add"><label className="field"><span>Добавить команду</span><select value={adding} onChange={e=>setAdding(e.target.value)}><option value="">Выберите команду</option>{outside.map(e=><option key={e.id} value={e.id}>{e.team.name}</option>)}</select></label>
   {groups&&<label className="field"><span>В группу</span><select value={target} onChange={e=>setTarget(e.target.value)}><option value="">Где меньше команд</option>{groups.map((_,i)=><option key={i} value={i+1}>{LETTERS[i]}</option>)}</select></label>}
   <button type="button" disabled={!adding||busy} onClick={()=>ask({op:'add',entry_id:adding,group_no:target?Number(target):undefined,label:`Добавить ${names[adding]}`})}>Добавить</button></div>}
  <ErrorBox error={error}/>
  {pending&&<Modal title={pending.change.label} sheet onClose={()=>setPending(null)}>
   <p>{pending.preview.kept||pending.preview.cancelled?`Сохранятся ${pending.preview.kept} ${plural(pending.preview.kept,'назначенный матч','назначенных матча','назначенных матчей')}, ${pending.preview.cancelled} будут отменены.`:'Назначенные матчи не затронуты.'}</p>
   <ErrorBox error={error}/><div className="setup-actions"><button type="button" className="primary" disabled={busy} onClick={apply}>Применить</button><button type="button" onClick={()=>setPending(null)}>Отмена</button></div></Modal>}
 </section>;
}
