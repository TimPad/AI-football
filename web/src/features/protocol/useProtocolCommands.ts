import {useEffect,useState} from 'react';import {api,post} from '../../api/client';import type {Match} from '../../api/domain';import {useAuth} from '../auth/Auth';import {BrowserOutbox,createCommandQueue,type CommandQueue} from './outbox';
export function useProtocolCommands(matchId:string){
 const {session}=useAuth();const [,rerender]=useState(0);const [queue,setQueue]=useState<CommandQueue>();const [store]=useState(()=>{try{return new BrowserOutbox(localStorage)}catch{return new BrowserOutbox({getItem:()=>{throw Error()},setItem:()=>{throw Error()},removeItem:()=>{throw Error()}})}});const [error,setError]=useState<unknown>();
 useEffect(()=>{if(!session)return;let active=true;let q:CommandQueue|undefined;let timers:ReturnType<typeof setTimeout>[]=[];
  api<Match>(`/matches/${matchId}`).then(view=>{if(!active)return;q=createCommandQueue({matchId,adminId:session.id,view,store,send:c=>post(`/matches/${matchId}/commands`,{request_id:c.requestId,expected_revision:c.expectedRevision,kind:c.kind,payload:c.payload}),refresh:()=>api(`/matches/${matchId}`),changed:()=>{if(active)rerender(v=>v+1)}});setQueue(q);q.heartbeat();if(q.items.length&&!q.blocked)q.retry().catch(()=>{});
   for(const delay of [1000,3000,10000])timers.push(setTimeout(()=>{if(q?.items[0]?.state==='uncertain'&&!q.blocked&&navigator.onLine)q.retry().catch(()=>{})},delay));
  }).catch(setError);
  const interval=setInterval(()=>q?.heartbeat(),5000);const storage=()=>q?.heartbeat();const online=()=>{if(q?.items[0]?.state==='uncertain')q.retry().catch(()=>{})};const unload=(e:BeforeUnloadEvent)=>{if(q?.items.length){e.preventDefault();e.returnValue=''}};
  window.addEventListener('storage',storage);window.addEventListener('online',online);window.addEventListener('beforeunload',unload);
  return()=>{active=false;q?.dispose();timers.forEach(clearTimeout);clearInterval(interval);window.removeEventListener('storage',storage);window.removeEventListener('online',online);window.removeEventListener('beforeunload',unload)};
 },[matchId,session?.id]);
 useEffect(()=>{if(!queue?.items.some(c=>c.state==='uncertain'))return;const timers=[1000,3000,10000].map(ms=>setTimeout(()=>{if(queue.items[0]?.state==='uncertain'&&!queue.blocked&&navigator.onLine)queue.retry().catch(()=>{})},ms));return()=>timers.forEach(clearTimeout)},[queue,queue?.items[0]?.requestId,queue?.items[0]?.state]);
 return {queue,store,error};
}
