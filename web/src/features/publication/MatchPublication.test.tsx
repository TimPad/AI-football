import {beforeEach,afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {MatchPublication} from './MatchPublication';

vi.mock('../auth/Auth',()=>({useAuth:()=>({session:{id:'admin-1'}})}));
const M='11111111-1111-4111-8111-111111111111',T='t1';
const match={id:M,tournament_id:T,revision:4,published_version_id:null,protocol:{draft:false},projection:{effective_score:{home:3,away:2}}};
const versions={items:[{id:'v1',number:1,confirmed_at:'2026-10-20T18:00:00Z',published_at:null}],total:1};
const overview={match_id:M,analysis_revision:3,active_run_id:'r-review',published_run_id:null,jobs:[],runs:[{id:'r-review',job_id:'j',status:'review',revision:1,passed:true,partial:true,created_at:'2026-10-20'}]};
const part={versions:[{id:'P',status:'confirmed',revision:3},{id:'P2',status:'confirmed',revision:4}]};
const actions={versions:[{id:'A',status:'confirmed',revision:2}]};
const saved={revision:7,match_id:M,participation_version_id:'P',action_version_id:'A',policy_approved:true};
const analytics={revision:7,public_snapshot_id:'B',private_snapshot_id:null,policy_approved:true,snapshots:[{snapshot_id:'B',scope:'public',calculated_at:'2026-10-20T10:00:00Z',published_at:'2026-10-20T10:05:00Z',stale:false,settings:{profile_id:'per10'}}],sources:[]};
type Call={path:string;method:string;body:unknown};
let calls:Call[]=[];
function stub(overrides:Record<string,unknown>={}){
 calls=[];
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const path=String(input).replace('/api/v1','');const method=init?.method??'GET';const body=init?.body?JSON.parse(String(init.body)):null;calls.push({path,method,body});
  for(const [k,v] of Object.entries(overrides))if(path.includes(k))return new Response(JSON.stringify(v));
  if(method==='POST'&&path.endsWith('/commands'))return new Response(JSON.stringify({...match,revision:5,published_version_id:'v1'}));
  if(method==='PUT')return new Response(JSON.stringify({...saved,revision:8}));
  const value=path.startsWith(`/public/matches/${M}`)&&!path.includes('/analysis')&&!path.includes('/ratings')?{id:M,home_name:'Север',away_name:'Юг',score:{home:null,away:null},public_protocol_id:null,tournament:{id:T}}
   :path.includes('/public/')?{error:{code:'not_found',message:'Нет'}}
   :path.includes('/versions')?versions:path.includes('/analysis')?overview:path.includes('/performance-publication')?saved
   :path.includes('/participation')?part:path.includes('/performance-actions')?actions:path.includes('/analytics')?analytics:match;
  return new Response(JSON.stringify(value),{status:path.includes('/public/')&&'error' in value?404:200});
 }));
}
const show=(canManage=true)=>render(<MemoryRouter><MatchPublication matchId={M} tournamentId={T} actorId="admin-1" canManage={canManage}/></MemoryRouter>);
beforeEach(()=>{localStorage.clear()});
afterEach(()=>vi.unstubAllGlobals());

describe('match publication',()=>{
 it('reads saved sources without writing and sends the tournament revision',async()=>{
  stub();const user=userEvent.setup();show();
  const partSelect=await screen.findByLabelText('Публикуемая версия участия');
  expect(partSelect).toHaveValue('P');
  expect(screen.getByLabelText('Публикуемая версия действий')).toHaveValue('A');
  expect(calls.filter(c=>c.method!=='GET')).toEqual([]);
  expect(calls.find(c=>c.path.endsWith('/performance-publication'))?.body).toBeNull();
  await user.selectOptions(partSelect,'P2');
  await user.click(screen.getByRole('button',{name:'Сохранить разрешение'}));
  await waitFor(()=>expect(calls.some(c=>c.method==='PUT')).toBe(true));
  const put=calls.find(c=>c.method==='PUT')!.body as Record<string,unknown>;
  expect(put).toMatchObject({expected_revision:7,expected_match_revision:4,participation_version_id:'P2',action_version_id:'A',approve_policy:true});
  expect(put.request_id).toBeTruthy();
 });
 it('keeps an unconfirmed CV blocked with a fix link while the protocol can be published',async()=>{
  stub();const user=userEvent.setup();show();
  const cv=await screen.findByRole('button',{name:'Опубликовать CV'});
  expect(cv).toBeDisabled();
  expect(screen.getByText(/Версия на проверке не подтверждена/).closest('p')!.querySelector('a')).toHaveAttribute('href','/?tab=review');
  expect(Object.keys(localStorage).some(k=>k.endsWith(':lease'))).toBe(false);
  await user.click(screen.getByRole('button',{name:'Опубликовать протокол'}));
  await waitFor(()=>expect(calls.some(c=>c.method==='POST'&&c.path.endsWith('/commands'))).toBe(true));
  const post=calls.find(c=>c.method==='POST')!.body as {kind:string;payload:{version_id:string}};
  expect(post).toMatchObject({kind:'publish',payload:{version_id:'v1'}});
  expect(calls.filter(c=>c.method==='POST'&&c.path.endsWith('/commands'))).toHaveLength(1);
 });
 it('does not queue a publication over an unsent protocol command',async()=>{
  localStorage.setItem(`aifootball:protocol:v1:admin-1:${M}`,JSON.stringify({version:1,items:[{matchId:M,requestId:'22222222-2222-4222-8222-222222222222',kind:'set_notes',payload:{notes:'x'},expectedRevision:4,state:'conflict',createdAt:'2026-10-20T15:00:00Z'}]}));
  stub();const user=userEvent.setup();show();
  await user.click(await screen.findByRole('button',{name:'Опубликовать протокол'}));
  expect(await screen.findByText(/неотправленная команда \(set_notes\)/)).toBeInTheDocument();
  expect(calls.some(c=>c.method==='POST')).toBe(false);
 });
 it('keeps the published edition and publishes a calculated one only on request',async()=>{
  stub({'/analytics':{...analytics,snapshots:[...analytics.snapshots,{snapshot_id:'C',scope:'public',calculated_at:'2026-10-21T10:00:00Z',published_at:null,stale:false,settings:{}}]}});
  const user=userEvent.setup();show();
  const row=(await screen.findByRole('heading',{name:'Рейтинг турнира'})).closest('article')!;
  expect(within(row).getByText(/издание B/)).toBeInTheDocument();
  expect(within(row).getByText(/издание C · рассчитано/)).toBeInTheDocument();
  expect(calls.some(c=>c.path.endsWith('/analytics/publish'))).toBe(false);
  await user.click(within(row).getByRole('button',{name:'Опубликовать издание'}));
  await waitFor(()=>expect(calls.find(c=>c.path.endsWith('/analytics/publish'))?.body).toMatchObject({expected_revision:7,snapshot_id:'C'}));
 });
 it('lets an ordinary admin see only the protocol and guest preview from public routes',async()=>{
  stub();show(false);
  expect(await screen.findByRole('button',{name:'Опубликовать протокол'})).toBeInTheDocument();
  await waitFor(()=>expect(document.querySelectorAll('.guest-sources .v')).toHaveLength(3));
  expect(document.querySelector('.guest-sources')).toHaveTextContent('не опубликован');
  expect(screen.queryByRole('button',{name:'Опубликовать CV'})).toBeNull();
  expect(calls.some(c=>/participation|performance|analytics|\/analysis/.test(c.path)&&!c.path.startsWith('/public/'))).toBe(false);
  const preview=calls.filter(c=>c.path.startsWith('/public/'));
  expect(preview.length).toBeGreaterThan(0);
 });
});
