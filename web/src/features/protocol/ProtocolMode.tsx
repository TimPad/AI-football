import {useAuth} from '../auth/Auth';
import {useDraft} from './drafts';

export type ProtocolModeKey='live'|'after'|'result';
const MODES:{id:ProtocolModeKey;label:string;hint:string}[]=[
 {id:'live',label:'Вести матч',hint:'События и ручные часы'},
 {id:'after',label:'Заполнить после матча',hint:'Внесите известные итоги и эпизоды из бумажного протокола'},
 {id:'result',label:'Только итог',hint:'Только счёт. Неизвестные события и полнота остаются неизвестными'},
];
const isMode=(v:unknown):v is ProtocolModeKey=>v==='live'||v==='after'||v==='result';

// Режим — локальное представление ввода; сохраняется в черновике администратора, на сервер не пишется.
export function useProtocolMode(matchId:string){
 const {session}=useAuth();
 return useDraft<ProtocolModeKey>(`aifootball:protocol-mode:v1:${session!.id}:${matchId}`,'live',isMode);
}

export function ModeSelector({value,onChange}:{value:ProtocolModeKey;onChange:(m:ProtocolModeKey)=>void}){
 return <div className="mode-row"><div className="segmented" role="group" aria-label="Режим ввода протокола">{MODES.map(m=>
  <button key={m.id} aria-pressed={value===m.id} className={value===m.id?'active':''} onClick={()=>onChange(m.id)}>{m.label}</button>)}</div>
  <span className="muted">{MODES.find(m=>m.id===value)!.hint}</span></div>;
}
