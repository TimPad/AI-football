let csrf='';
export const setCsrf=(value:string)=>{csrf=value};
export class ApiError extends Error{
 constructor(public code:string,message:string,public fields:Record<string,string>={},public currentRevision?:number,public status=0){super(message)}
}
export async function api<T>(path:string,options:RequestInit={}):Promise<T>{
 const headers=new Headers(options.headers);
 if(options.body && typeof options.body==='string')headers.set('Content-Type','application/json');
 if(options.method && !['GET','HEAD'].includes(options.method))headers.set('X-CSRF-Token',csrf);
 let response:Response;
 try{response=await fetch(`/api/v1${path}`,{...options,headers,credentials:'same-origin'})}catch{throw new ApiError('network','Не удалось связаться с сервером. Правки сохранены в этом браузере.')}
 if(!response.ok){
  let error;try{error=(await response.json()).error}catch{error=null}
  if(response.status===401)window.dispatchEvent(new Event('session-expired'));
  throw new ApiError(error?.code??'request',error?.message??`Ошибка сервера (${response.status})`,error?.fields??{},error?.current_revision,response.status);
 }
 return response.status===204 ? undefined as T : response.json();
}
export const post=<T>(path:string,body:unknown)=>api<T>(path,{method:'POST',body:JSON.stringify(body)});
export async function all<T>(path:string):Promise<T[]>{
 const items:T[]=[];let total=Infinity;
 while(items.length<total){const page=await api<{items:T[],total:number}>(`${path}${path.includes('?')?'&':'?'}limit=100&offset=${items.length}`);total=page.total;items.push(...page.items);if(!page.items.length)break}
 return items;
}
export const errorText=(e:unknown)=>e instanceof ApiError? [e.message,...Object.values(e.fields)].join(' · '):e instanceof Error?e.message:'Не удалось сохранить';
