import {it,expect,vi,afterEach} from 'vitest';
import {api,ApiError,setCsrf} from './client';
afterEach(()=>vi.unstubAllGlobals());
it('treats a truncated success body as an ambiguous response, preserving safe retry semantics',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{', {status:201,headers:{'Content-Type':'application/json'}})));
 const error=await api('/halls',{method:'POST',body:'{}'}).catch(e=>e);
 expect(error).toBeInstanceOf(ApiError);
 if(!(error instanceof ApiError))throw error;
 expect(error.code).toBe('network');
});
it('keeps administrative and captain request tokens separate',async()=>{
 const values:string[]=[];vi.stubGlobal('fetch',vi.fn(async(_path,init)=>{values.push(new Headers(init.headers).get('X-CSRF-Token')??'');return new Response('{}')}));
 setCsrf('admin');setCsrf('captain','captain');await api('/teams',{method:'POST',body:'{}'});await api('/captain/teams',{method:'POST',body:'{}'});expect(values).toEqual(['admin','captain']);
});
it('does not expire a new session for an old response',async()=>{
 let release:((r:Response)=>void)|undefined;const expired=vi.fn();window.addEventListener('session-expired',expired);
 vi.stubGlobal('fetch',vi.fn(()=>new Promise<Response>(r=>{release=r})));setCsrf('old','captain');const read=api('/captain/teams').catch(()=>{});setCsrf('new','captain');release!(new Response('{}',{status:401}));await read;expect(expired).not.toHaveBeenCalled();window.removeEventListener('session-expired',expired);
});
