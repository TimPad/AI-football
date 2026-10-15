import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import {ProtocolSession,useProtocolSession} from './ProtocolSession';
import {storageKey} from './outbox';

vi.mock('../auth/Auth',()=>({useAuth:()=>({session:{id:'admin-1'}})}));
const M='11111111-1111-4111-8111-111111111111';
const REQUEST='22222222-2222-4222-8222-222222222222';
const view={id:M,revision:4,tournament_id:'t',protocol:{draft:true}};
const seeded={matchId:M,requestId:REQUEST,kind:'set_notes',payload:{notes:'Пауза из-за света'},expectedRevision:4,state:'queued',createdAt:'2026-10-20T15:00:00Z'};

function Probe(){const {queue}=useProtocolSession();return <p>{queue?`в очереди: ${queue.items.length}`:'загрузка'}</p>}
beforeEach(()=>localStorage.clear());
afterEach(()=>vi.unstubAllGlobals());

describe('protocol session',()=>{
 it('keeps the pending command across leaving the task and resends the same envelope once',async()=>{
  localStorage.setItem(storageKey('admin-1',M),JSON.stringify({version:1,items:[seeded]}));
  const posts:{request_id:string;expected_revision:number;kind:string;payload:unknown}[]=[];
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
   if(init?.method==='POST'){posts.push(JSON.parse(String(init.body)));
    if(posts.length===1)throw new TypeError('lost');
    return new Response(JSON.stringify({...view,revision:5}))}
   return new Response(JSON.stringify(view));
  }));
  const first=render(<ProtocolSession matchId={M}><Probe/></ProtocolSession>);
  await waitFor(()=>expect(posts).toHaveLength(1));
  expect(await screen.findByText('в очереди: 1')).toBeInTheDocument();
  first.unmount();
  // Переход в отчёт/публикацию: очередь размонтирована, но не очищена.
  expect(JSON.parse(localStorage.getItem(storageKey('admin-1',M))!).items[0].requestId).toBe(REQUEST);
  render(<ProtocolSession matchId={M}><Probe/></ProtocolSession>);
  expect(await screen.findByText('в очереди: 0')).toBeInTheDocument();
  expect(posts).toHaveLength(2);
  expect(posts[1]).toEqual(posts[0]);
  expect(posts[0]).toMatchObject({request_id:REQUEST,kind:'set_notes',payload:{notes:'Пауза из-за света'}});
 });
 it('refuses to be used outside a session',()=>{
  vi.spyOn(console,'error').mockImplementation(()=>{});
  expect(()=>render(<Probe/>)).toThrow('ProtocolSession is required');
 });
});
