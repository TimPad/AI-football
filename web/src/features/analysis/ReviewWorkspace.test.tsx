import {beforeEach,describe,expect,it,vi} from 'vitest';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {MemoryRouter,Route,Routes,useLocation,useNavigate} from 'react-router-dom';
import type {AnalysisRun} from '../../api/domain';
vi.mock('../../api/client',async()=>{const actual=await vi.importActual<typeof import('../../api/client')>('../../api/client');return {...actual,api:vi.fn(),post:vi.fn()}});
import {api} from '../../api/client';
import {IdentityReview} from './IdentityReview';
import {ReviewWorkspace} from './ReviewWorkspace';

const base={job_id:'job',match_id:'match',revision:0,analysis_revision:0,status:'review',source_run_id:null,created_at:'2026-10-13',partial:true,passed:true,
 active_run_id:null,published_run_id:null,manifest:{source_video:{duration_s:240}},report:{match:{processed_s:120},pitch:{length_m:40,width_m:20},periods:[]},
 checks:{partial:true,passed:true,warnings:[],critical_errors:[]},context:{match_id:'match',hall_id:'hall',camera:{},units:{},pitch:{length_m:40,width_m:20},
  teams:{home:{id:'team1',name:'Север'},away:{id:'team2',name:'Юг'}},
  rosters:[{player_id:'p7',side:'home',display_name:'Иван Петров',shirt_number:'7'},{player_id:'p9',side:'home',display_name:'Пётр Сидоров',shirt_number:'9'}]},
 side_map:{A:'home',B:'away'},players:[]};
const tracks=(n:number)=>Array.from({length:n},(_,i)=>({track_id:i+1,team:'A',role:'player',intervals:[[i*10,i*10+5]],thumb:null,has_metrics:true}));
const runA={...base,id:'run-a',tracks:tracks(51),assignments:[{track_id:30,player_id:'p9'},{track_id:31,excluded_reason:'судья'}]} as unknown as AnalysisRun;
const runB={...base,id:'run-b',tracks:tracks(2),assignments:[]} as unknown as AnalysisRun;
beforeEach(()=>{localStorage.clear();vi.clearAllMocks()});

describe('identity review queue',()=>{
 it('saves hidden assignments after filtering and paging',async()=>{
  const save=vi.fn().mockResolvedValue(undefined);
  render(<MemoryRouter><IdentityReview run={runA} actorId="admin" editable onSave={save}/></MemoryRouter>);
  expect(screen.getByLabelText('Фильтр треков')).toHaveValue('unassigned');
  fireEvent.change(screen.getByLabelText('Игрок фрагмента 1'),{target:{value:'p7'}});
  fireEvent.change(screen.getByLabelText('Фильтр треков'),{target:{value:'all'}});
  fireEvent.click(screen.getByRole('button',{name:'Следующая страница'}));
  fireEvent.click(screen.getByRole('button',{name:'Следующая страница'}));
  const queue=screen.getByRole('navigation',{name:'Очередь треков'});
  expect(within(queue).getByText('41–51 из 51')).toBeInTheDocument();
  fireEvent.click(within(queue).getByRole('button',{name:/Трек 51/}));
  fireEvent.change(screen.getByLabelText('Игрок фрагмента 51'),{target:{value:'p7'}});
  fireEvent.click(screen.getByRole('button',{name:'Сохранить сопоставление'}));
  await waitFor(()=>expect(save).toHaveBeenCalled());
  const sent=save.mock.calls[0][0].assignments as {track_id:number}[];
  expect(sent.map(a=>a.track_id).sort((a,b)=>a-b)).toEqual([1,30,31,51]);
  expect(sent).toContainEqual({track_id:31,excluded_reason:'судья'});
 });
 it('keeps drafts scoped to their run and shows missing frames honestly',()=>{
  const save=vi.fn();
  const first=render(<MemoryRouter><IdentityReview run={runA} actorId="admin" editable onSave={save}/></MemoryRouter>);
  fireEvent.change(screen.getByLabelText('Игрок фрагмента 1'),{target:{value:'p7'}});
  expect(screen.getAllByText('Кадр недоступен').length).toBeGreaterThan(0);
  first.unmount();
  const second=render(<MemoryRouter><IdentityReview run={runB} actorId="admin" editable onSave={save}/></MemoryRouter>);
  expect(screen.getByLabelText('Игрок фрагмента 1')).toHaveValue('');
  second.unmount();
  render(<MemoryRouter><IdentityReview run={runA} actorId="admin" editable onSave={save}/></MemoryRouter>);
  fireEvent.change(screen.getByLabelText('Фильтр треков'),{target:{value:'assigned'}});
  fireEvent.click(within(screen.getByRole('navigation',{name:'Очередь треков'})).getByRole('button',{name:/Трек 1/}));
  expect(screen.getByLabelText('Игрок фрагмента 1')).toHaveValue('p7');
 });
 it('never treats a number hint as an assignment',()=>{
  render(<MemoryRouter><IdentityReview run={runB} actorId="admin" editable onSave={vi.fn()} suggestions={[{track_id:1,player_id:'p7',number:'7',status:'candidate',reasons:['Номер виден на 3 кадрах'],evidence_ids:[]}]}/></MemoryRouter>);
  expect(screen.getByText(/Подсказка, требует проверки/)).toBeInTheDocument();
  expect(screen.getByLabelText('Игрок фрагмента 1')).toHaveValue('');
  expect(screen.getByRole('radio',{name:/Неизвестный участник/})).toBeChecked();
 });
});

describe('review workspace URL',()=>{
 let search='';
 function Probe(){search=useLocation().search;return null}
 function Pick({to}:{to:string}){const go=useNavigate();return <button onClick={()=>go(to)}>{to}</button>}
 it('keeps the selected run when an older run responds late and blocks confirmation while dirty',async()=>{
  let releaseA!:(v:AnalysisRun)=>void;
  vi.mocked(api).mockImplementation(async(path:string)=>{
   if(path.endsWith('/analysis'))return {match_id:'match',analysis_revision:0,active_run_id:'run-a',published_run_id:null,jobs:[],
    runs:[{id:'run-a',job_id:'job',status:'review',revision:0,created_at:'2026-10-13'},{id:'run-b',job_id:'job',status:'review',revision:0,created_at:'2026-10-14'}]};
   if(path.endsWith('/runs/run-a'))return new Promise<AnalysisRun>(r=>{releaseA=r});
   if(path.endsWith('/runs/run-b'))return runB;
   throw new Error('unexpected '+path);
  });
  render(<MemoryRouter initialEntries={['/m?tab=review']}><Routes><Route path="/m" element={<><ReviewWorkspace matchId="match" actorId="admin" canManage/><Probe/><Pick to="/m?tab=review&run_id=run-b"/></>}/></Routes></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button',{name:'/m?tab=review&run_id=run-b'}));
  expect(await screen.findByText(/фрагментов: 2/)).toBeInTheDocument();
  releaseA(runA);await new Promise(r=>setTimeout(r,10));
  expect(screen.queryByText(/фрагментов: 51/)).toBeNull();
  fireEvent.change(screen.getByLabelText('Игрок фрагмента 1'),{target:{value:'p7'}});
  expect(screen.getByRole('button',{name:'Подтвердить аналитику'})).toBeDisabled();
  fireEvent.click(within(screen.getByRole('navigation',{name:'Очередь треков'})).getByRole('button',{name:/Трек 2/}));
  expect(new URLSearchParams(search).get('item_id')).toBe('2');
  expect(new URLSearchParams(search).get('run_id')).toBe('run-b');
  expect(vi.mocked(api).mock.calls.some(([p])=>String(p).includes('understanding'))).toBe(false);
 });
});
