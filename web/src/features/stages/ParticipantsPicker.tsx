import type {Entry} from '../../api/domain';

const KEY=(tid:string)=>`aifootball:participants:${tid}`;
// «Кто играет» запоминается в браузере организатора, чтобы подсказки и жеребьёвка видели один и тот же состав.
export function storedParticipants(tid:string,entries:Entry[]):string[]{
 try{const raw=localStorage.getItem(KEY(tid));const ids=raw?JSON.parse(raw):null;if(Array.isArray(ids)){const known=ids.filter((id:unknown)=>entries.some(e=>e.id===id));if(known.length>=2)return known}}catch{/* хранилище недоступно */}
 return entries.map(e=>e.id);
}
export function storeParticipants(tid:string,ids:string[]){try{localStorage.setItem(KEY(tid),JSON.stringify(ids))}catch{/* хранилище недоступно */}}

export function ParticipantsPicker({entries,value,onChange}:{entries:Entry[];value:string[];onChange:(ids:string[])=>void}){
 const all=value.length===entries.length;
 const toggle=(id:string)=>onChange(value.includes(id)?value.filter(v=>v!==id):entries.map(e=>e.id).filter(e=>e===id||value.includes(e)));
 return <fieldset className="participants"><legend>Кто играет · {value.length} из {entries.length}</legend>
  <label className="participant"><input type="checkbox" checked={all} onChange={()=>onChange(all?[]:entries.map(e=>e.id))}/><span>Выбрать всех</span></label>
  {entries.map(e=><label key={e.id} className="participant"><input type="checkbox" checked={value.includes(e.id)} onChange={()=>toggle(e.id)}/><span>{e.team.name}</span></label>)}
  {value.length<2&&<p className="warning" role="status">Для турнира нужны минимум две команды.</p>}
 </fieldset>;
}
