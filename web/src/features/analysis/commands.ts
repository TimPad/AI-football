import {api,ApiError} from '../../api/client';
export type Pending={path:string,method:string,body:Record<string,unknown>};
export function readPending(key:string):Pending|null{
 const raw=localStorage.getItem(key);if(!raw)return null;
 const p=JSON.parse(raw);if(typeof p.path!=='string'||!['POST','PUT'].includes(p.method)||!p.body||typeof p.body.request_id!=='string')throw Error('Повреждена сохранённая команда. Скачайте её перед очисткой.');return p;
}
export function prepare(key:string,path:string,body:Record<string,unknown>,method='POST'):Pending{
 const old=readPending(key);
 if(old){const {request_id:_,...oldBody}=old.body;if(old.path!==path||old.method!==method||JSON.stringify(oldBody)!==JSON.stringify(body))throw new ApiError('pending','Есть незавершённая отправка. Повторите её или скачайте и снимите блокировку.');return old}
 const pending={path,method,body:{...body,request_id:crypto.randomUUID()}};
 localStorage.setItem(key,JSON.stringify(pending));return pending;
}
export async function retryJson<T>(key:string,pending:Pending):Promise<T>{
 const result=await api<T>(pending.path,{method:pending.method,body:JSON.stringify(pending.body)});localStorage.removeItem(key);return result;
}
export async function sendJson<T>(key:string,path:string,body:Record<string,unknown>,method='POST'){
 return retryJson<T>(key,prepare(key,path,body,method));
}
