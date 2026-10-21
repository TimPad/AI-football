const csrf={admin:'',captain:''};
export const setCsrf=(value:string,audience:'admin'|'captain'='admin')=>{csrf[audience]=value};
export class ApiError extends Error{
 constructor(public code:string,message:string,public fields:Record<string,string>={},public currentRevision?:number,public status=0){super(message)}
}
export async function api<T>(path:string,options:RequestInit={}):Promise<T>{
 const headers=new Headers(options.headers);const audience=path.startsWith('/captain/')?'captain':'admin';const requestCsrf=csrf[audience];
 if(options.body && typeof options.body==='string')headers.set('Content-Type','application/json');
 if(options.method && !['GET','HEAD'].includes(options.method))headers.set('X-CSRF-Token',requestCsrf);
 let response:Response;
 try{response=await fetch(`/api/v1${path}`,{...options,signal:options.signal??AbortSignal.timeout(30000),headers,credentials:'same-origin'})}catch{throw new ApiError('network','Не удалось связаться с сервером. Правки сохранены в этом браузере.')}
 if(!response.ok){
  let error;try{error=(await response.json()).error}catch{error=null}
  if(response.status===401&&requestCsrf===csrf[audience]&&!path.endsWith('/auth/me'))window.dispatchEvent(new CustomEvent('session-expired',{detail:{audience}}));
  throw new ApiError(error?.code??'request',error?.message??`Ошибка сервера (${response.status})`,error?.fields??{},error?.current_revision,response.status);
 }
 if(response.status===204)return undefined as T;
 // A successful mutation can be committed even if its body is lost. Keep
 // this error in the same retry category as a transport interruption.
 try{return await response.json()}catch{throw new ApiError('network','Ответ сервера получен не полностью. Повторите сохранение с тем же ключом отправки.')}
}
export const post=<T>(path:string,body:unknown)=>api<T>(path,{method:'POST',body:JSON.stringify(body)});
export async function all<T>(path:string):Promise<T[]>{
 const items:T[]=[];let total=Infinity;
 while(items.length<total){const page=await api<{items:T[],total:number}>(`${path}${path.includes('?')?'&':'?'}limit=100&offset=${items.length}`);total=page.total;items.push(...page.items);if(!page.items.length)break}
 return items;
}
export const errorText=(e:unknown)=>typeof e==='string'?e:e instanceof ApiError? [e.message,...Object.values(e.fields)].join(' · '):e instanceof Error?e.message:'Не удалось сохранить';
