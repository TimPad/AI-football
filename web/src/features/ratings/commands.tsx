import {useState} from 'react';
import {ErrorBox,downloadJson} from '../../components/ui';
import {readPending,sendJson,retryJson,type Pending} from '../analysis/commands';
export function useRatingCommand<T>(key:string,onSaved:(v:T)=>void){
 const [pending,setPending]=useState<Pending|null>(()=>{try{return readPending(key)}catch{return null}});
 const [corrupt,setCorrupt]=useState(()=>{try{readPending(key);return false}catch{return true}});
 const [busy,setBusy]=useState(false);const [error,setError]=useState<unknown>();
 async function execute(path:string,body:Record<string,unknown>,method='POST',retry=false){setBusy(true);setError(undefined);try{
  const result=retry&&pending?await retryJson<T>(key,pending):await sendJson<T>(key,path,body,method);onSaved(result);return result;
 }catch(e){setError(e);return undefined}finally{try{setPending(readPending(key))}catch{setCorrupt(true)}setBusy(false)}}
 return {pending,corrupt,busy,error,locked:busy||!!pending||corrupt,execute,
  retry:()=>void execute('',{},'POST',true),reset:()=>{downloadJson(localStorage.getItem(key),'команда-рейтинга.json');localStorage.removeItem(key);setPending(null);setCorrupt(false)}};
}
export function CommandStatus({command}:{command:ReturnType<typeof useRatingCommand<unknown>>}){return <><ErrorBox error={command.error}/>{command.pending&&<div className="draft-banner"><p>Команда сохранена. Повтор использует прежний ключ отправки.</p><button disabled={command.busy} onClick={command.retry}>Повторить отправку</button><button disabled={command.busy} onClick={command.reset}>Скачать команду и снять блокировку</button></div>}{command.corrupt&&<button onClick={command.reset}>Скачать и очистить повреждённую команду</button>}</>}
