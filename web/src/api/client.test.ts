import {it,expect,vi,afterEach} from 'vitest';
import {api,ApiError} from './client';
afterEach(()=>vi.unstubAllGlobals());
it('treats a truncated success body as an ambiguous response, preserving safe retry semantics',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{', {status:201,headers:{'Content-Type':'application/json'}})));
 const error=await api('/halls',{method:'POST',body:'{}'}).catch(e=>e);
 expect(error).toBeInstanceOf(ApiError);
 if(!(error instanceof ApiError))throw error;
 expect(error.code).toBe('network');
});
