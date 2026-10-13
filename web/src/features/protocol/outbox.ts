import type {DraftCommand,Match} from '../../api/domain';import {ApiError} from '../../api/client';
export type QueuedCommand=DraftCommand & {matchId:string,requestId:string,expectedRevision:number|null,state:'queued'|'sending'|'uncertain'|'conflict'|'invalid'|'auth',createdAt:string};
interface Store{error?:string;load:(mid:string,admin:string)=>QueuedCommand[];save:(mid:string,admin:string,items:QueuedCommand[])=>void;claim:(key:string,owner:string,take?:boolean)=>boolean;release:(key:string,owner:string)=>void}
export class MemoryOutbox implements Store{
 error?:string;private data=new Map<string,QueuedCommand[]>();protected leases=new Map<string,{owner:string,until:number}>();
 load(mid:string,admin:string){return structuredClone(this.data.get(`${admin}:${mid}`)??[])}
 save(mid:string,admin:string,items:QueuedCommand[]){this.data.set(`${admin}:${mid}`,structuredClone(items))}
 claim(key:string,owner:string,take=false){const old=this.leases.get(key);if(!take&&old&&old.owner!==owner&&old.until>Date.now())return false;this.leases.set(key,{owner,until:Date.now()+15000});return true}
 release(key:string,owner:string){if(this.leases.get(key)?.owner===owner)this.leases.delete(key)}
}
const commandKinds=new Set(['update_match','set_lineup','set_status','add_event','replace_event','remove_event','set_totals','set_completeness','set_notes','confirm','reopen','publish','unpublish','remove_attachment','clock_start','clock_pause','clock_resume','clock_set','clock_end_period']);
export const storageKey=(admin:string,mid:string)=>`aifootball:protocol:v1:${admin}:${mid}`;
export class BrowserOutbox extends MemoryOutbox{
 raw:string|null=null;
 constructor(private storage:Pick<Storage,'getItem'|'setItem'|'removeItem'>){super()}
 load(mid:string,admin:string){try{const raw=this.storage.getItem(storageKey(admin,mid));if(!raw)return super.load(mid,admin);this.raw=raw;const data=JSON.parse(raw);if(data.version!==1||!Array.isArray(data.items)||data.items.length>1000||!data.items.every((c:QueuedCommand)=>c.matchId===mid&&/^[0-9a-f-]{36}$/i.test(c.requestId)&&commandKinds.has(c.kind)&&c.payload&&typeof c.payload==='object'&&!Array.isArray(c.payload)&&['queued','sending','uncertain','conflict','invalid','auth'].includes(c.state)&&(c.expectedRevision===null||Number.isSafeInteger(c.expectedRevision)&&c.expectedRevision>=0)))throw new Error('invalid');super.save(mid,admin,data.items);return data.items.map((c:QueuedCommand)=>({...c,state:c.state==='sending'?'uncertain':c.state}))}catch{this.error='Повреждена локальная копия. Скачайте её перед очисткой; отправка остановлена.';return []}}
 save(mid:string,admin:string,items:QueuedCommand[]){super.save(mid,admin,items);if(this.error?.startsWith('Повреждена'))return;try{this.storage.setItem(storageKey(admin,mid),JSON.stringify({version:1,items}));this.error=undefined}catch{this.error='Локальная копия недоступна. Правки остаются только в памяти; скачайте JSON перед закрытием.'}}
 claim(key:string,owner:string,take=false){if(this.error?.startsWith('Повреждена'))return false;try{const raw=this.storage.getItem(key+':lease');const old=raw?JSON.parse(raw):null;if(!take&&old&&old.owner!==owner&&old.until>Date.now())return false;this.storage.setItem(key+':lease',JSON.stringify({owner,until:Date.now()+15000}));return JSON.parse(this.storage.getItem(key+':lease')??'null')?.owner===owner}catch{return super.claim(key,owner,take)}}
 release(key:string,owner:string){try{const old=JSON.parse(this.storage.getItem(key+':lease')??'null');if(old?.owner===owner)this.storage.removeItem(key+':lease')}catch{}super.release(key,owner)}
 clearCorrupt(mid:string,admin:string){this.storage.removeItem(storageKey(admin,mid));this.error=undefined;this.raw=null}
}
export function createCommandQueue(opts:{matchId:string,adminId:string,view:Match,store:Store,send:(c:QueuedCommand)=>Promise<Match>,refresh:()=>Promise<Match>,changed?:()=>void}){
 const {matchId,adminId,store}=opts;const key=storageKey(adminId,matchId);const owner=crypto.randomUUID();let running=false;let closed=false;let needRefresh=false;
 const queue={view:opts.view,items:store.load(matchId,adminId),blocked:false,error:undefined as unknown,lastRequestId:'',
  async enqueue(d:DraftCommand){if(!store.claim(key,owner)) {queue.blocked=true;notify();throw new Error('Матч открыт в другом окне. Перейдите туда или возьмите управление.')}const c={...structuredClone(d),matchId,requestId:crypto.randomUUID(),expectedRevision:null,state:'queued' as const,createdAt:new Date().toISOString()};queue.lastRequestId=c.requestId;queue.items.push(c);persist();await pump()},
  async retry(){if(queue.items[0]?.state==='conflict'||queue.items[0]?.state==='invalid')return;await pump()},
  async resolveConflict(choice:'replace'|'discard'){if(running)return;queue.view=await opts.refresh();const c=queue.items.shift();if(choice==='replace'&&c)queue.items.unshift({...c,requestId:crypto.randomUUID(),expectedRevision:null,state:'queued'});queue.error=undefined;persist();await pump()},
  async refresh(){queue.view=await opts.refresh();notify()},
  async takeOver(){if(running)return;store.claim(key,owner,true);queue.blocked=false;queue.items=store.load(matchId,adminId);notify();await queue.retry()},
  heartbeat(){if(!closed){queue.blocked=!store.claim(key,owner);notify()}},
  dispose(){closed=true;store.release(key,owner)},
 };
 function notify(){opts.changed?.()}
 function persist(){store.save(matchId,adminId,queue.items);notify()}
 async function pump(){if(running||closed)return;if(!store.claim(key,owner)){queue.blocked=true;notify();throw new Error('Матч открыт в другом окне.')}queue.blocked=false;running=true;
  try{if(needRefresh){queue.view=await opts.refresh();needRefresh=false;notify()}
   while(queue.items.length&&!closed){const c=queue.items[0];if(['conflict','invalid'].includes(c.state))break;
    if(c.expectedRevision===null){queue.view=await opts.refresh();c.expectedRevision=queue.view.revision;persist()}
    // Persist immutable retry envelope before the network request. UI state may change, payload/revision may not.
    c.state='sending';persist();queue.error=undefined;
    try{const saved=await opts.send(c);queue.view=saved;queue.items.shift();persist();needRefresh=true;queue.view=await opts.refresh();needRefresh=false;notify()}
    catch(e){queue.error=e;if(queue.items[0]===c){c.state=e instanceof ApiError&&e.status===409?'conflict':e instanceof ApiError&&e.status===422?'invalid':e instanceof ApiError&&e.status===401?'auth':'uncertain';persist();if(c.state==='conflict'){try{queue.view=await opts.refresh();notify()}catch{}}}throw e}
   }
  }finally{running=false;notify()}
 }
 return queue;
}
export type CommandQueue=ReturnType<typeof createCommandQueue>;
