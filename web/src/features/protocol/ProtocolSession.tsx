import {createContext,useContext,useState,type ReactNode} from 'react';
import {Download,RotateCcw} from 'lucide-react';
import type {DraftCommand} from '../../api/domain';
import {useAuth} from '../auth/Auth';
import {ErrorBox,Loading,downloadJson} from '../../components/ui';
import {useProtocolCommands} from './useProtocolCommands';

type ProtocolSessionValue=ReturnType<typeof useProtocolCommands>;
const SessionContext=createContext<ProtocolSessionValue|null>(null);

// Единственный владелец очереди команд протокола в редактирующих задачах матча.
// Отчёт и публикация её не создают; outbox сохраняется в localStorage между задачами.
export function ProtocolSession({matchId,children}:{matchId:string;children:ReactNode}){
 const value=useProtocolCommands(matchId);
 return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
export function useProtocolSession():ProtocolSessionValue{
 const value=useContext(SessionContext);
 if(!value)throw new Error('ProtocolSession is required');
 return value;
}

export function useSessionDispatch(){
 const {queue}=useProtocolSession();const [error,setError]=useState<unknown>();
 async function dispatch(d:DraftCommand){setError(undefined);try{await queue!.enqueue(d)}catch(e){setError(e);throw e}}
 return {dispatch,error,setError};
}

// Сохранение, блокировка другой вкладкой, конфликт и повреждённая копия видны в каждой редактирующей задаче.
export function SessionChrome({extra,children}:{extra?:unknown;children:(state:{disabled:boolean;readOnly:boolean})=>ReactNode}){
 const state=useProtocolSession();const {session}=useAuth();const [error,setError]=useState<unknown>();
 const queue=state.queue;
 if(!queue)return <Loading error={state.error}/>;
 const m=queue.view;const pending=!!queue.items.length;
 const blocked=queue.blocked||!!state.store.error?.startsWith('Повреждена');
 const disabled=pending||blocked;const head=queue.items[0];
 return <>
  <div className="save-state" role="status"><span>{blocked?'Открыто в другом окне':pending?`Несохранённых правок: ${queue.items.length}`:'Все изменения сохранены'}</span>
   <div className="row">{pending&&<button onClick={()=>queue.retry().catch(setError)} disabled={head.state==='conflict'||head.state==='invalid'}><RotateCcw/>Повторить</button>}
    {/* Копия нужна, только пока есть неотправленные правки (например, пропала связь в зале). */}
    {pending&&<button onClick={()=>downloadJson({commands:queue.items,raw:state.store.raw,extra})}><Download/>Сохранить копию правок</button>}
    <button disabled={pending} onClick={()=>queue.refresh().catch(setError)}>Обновить</button></div></div>
  <ErrorBox error={error||queue.error||state.store.error}/>
  {queue.blocked&&<div className="surface"><p>В другом окне этого браузера уже редактируется матч. Перед продолжением убедитесь, что там нет несохранённого ввода.</p><button onClick={()=>queue.takeOver().catch(setError)}>Взять управление в этом окне</button></div>}
  {state.store.error?.startsWith('Повреждена')&&<button onClick={()=>{downloadJson(state.store.raw,'повреждённая-копия.json');state.store.clearCorrupt(m.id,session!.id);queue.takeOver().catch(setError)}}>Скачать и очистить повреждённую копию</button>}
  {head&&['conflict','invalid'].includes(head.state)&&<section className="surface conflict"><h2>{head.state==='conflict'?'Конфликт изменений':'Проверьте локальную правку'}</h2>
   <p>Серверная ревизия: {m.revision}. Счёт: {m.projection.effective_score.home??'—'} : {m.projection.effective_score.away??'—'}. Локальное изменение: {head.kind}.</p>
   <details><summary>Локальный ввод</summary><pre>{JSON.stringify(head.payload,null,2)}</pre></details>
   <div className="row">{head.state==='conflict'&&<button onClick={()=>queue.resolveConflict('replace').catch(setError)}>Применить как новое изменение</button>}
    <button onClick={()=>{downloadJson(queue.items);queue.resolveConflict('discard').catch(setError)}}>Скачать правку и оставить серверную версию</button></div></section>}
  {children({disabled,readOnly:disabled||!m.protocol.draft})}
 </>;
}
