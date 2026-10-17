import {beforeEach,describe,expect,it,vi} from 'vitest';
import {fireEvent,render,screen,within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import type {AnalysisRun} from '../../api/domain';
import {IdentityReview} from './IdentityReview';
import {clashes,candidatesOf,baseGroups,assignGroup} from './candidates';

const track=(id:number,team:string,from:number,to:number,role='player')=>({track_id:id,team,role,intervals:[[from,to]],thumb:null,has_metrics:true});
const run={job_id:'job',match_id:'match',id:'run',revision:0,status:'review',
 context:{teams:{home:{id:'t1',name:'Север'},away:{id:'t2',name:'Юг'}},
  rosters:[{player_id:'p7',side:'home',display_name:'Иван Петров',shirt_number:'7'},{player_id:'p9',side:'home',display_name:'Пётр Сидоров',shirt_number:'9'},
   {player_id:'p1',side:'away',display_name:'Олег Юрьев',shirt_number:'1'}]},
 side_map:{A:'home',B:'away'},assignments:[],
 // Склейка: 1→2→3 — один игрок A; 4 — другой игрок A (весь фрагмент); 5 — B; 6 — короткий; 9 — судья.
 tracks:[track(1,'A',0,40),track(2,'A',40.5,90),track(3,'A',91,150),track(4,'A',0,150),track(5,'B',0,150,'goalkeeper'),track(6,'A',150,155),track(9,'',0,150,'referee')],
 groups:[[1,2,3]]} as unknown as AnalysisRun;
const suggestions=[{track_id:2,player_id:'p7',number:'7',status:'suggested',reasons:[],evidence_ids:[]}];
beforeEach(()=>localStorage.clear());

describe('player candidates',()=>{
 it('groups tracks into candidates and assigns a whole chain with one choice',()=>{
  const save=vi.fn().mockResolvedValue(undefined);
  render(<MemoryRouter><IdentityReview run={run} actorId="admin" editable onSave={save} suggestions={suggestions}/></MemoryRouter>);
  // Склейка есть — открывается режим «По игрокам»: 4 кандидата игроков вместо 6 треков, судья не в списке.
  expect(screen.getByRole('button',{name:'По игрокам · 4'})).toHaveAttribute('aria-pressed','true');
  const home=screen.getByRole('region',{name:'Кандидаты команды A'});
  expect(within(home).getByText('3 фрагмента')).toBeInTheDocument();
  expect(within(home).getByText('Короткие фрагменты · 1')).toBeInTheDocument();
  expect(screen.getByRole('region',{name:'Кандидаты команды B'})).toHaveTextContent('вероятно вратарь');
  // Номер прочитан на одном фрагменте — подсказка для всего кандидата.
  fireEvent.click(screen.getByRole('button',{name:'Принять все подсказки'}));
  fireEvent.change(screen.getByLabelText('Игрок кандидата 4'),{target:{value:'p9'}});
  fireEvent.click(screen.getByRole('button',{name:'Сохранить сопоставление'}));
  expect(save.mock.calls[0][0].assignments).toEqual(expect.arrayContaining([
   {track_id:1,player_id:'p7'},{track_id:2,player_id:'p7'},{track_id:3,player_id:'p7'},{track_id:4,player_id:'p9'}]));
  expect(save.mock.calls[0][0].assignments).toHaveLength(4);
 });

 it('splits a wrong chain and merges pieces that are never on the pitch together',()=>{
  render(<MemoryRouter><IdentityReview run={run} actorId="admin" editable onSave={vi.fn()}/></MemoryRouter>);
  fireEvent.click(screen.getByRole('button',{name:'Разделить'}));
  expect(screen.getByRole('button',{name:'По игрокам · 4'})).toBeInTheDocument();
  const home=screen.getByRole('region',{name:'Кандидаты команды A'});
  expect(within(home).queryByText('3 фрагмента')).toBeNull();
  // Трек 4 виден всё время — с ним объединить нельзя; фрагмент 2 с 3 — можно.
  const options=[...(screen.getByLabelText('Объединить кандидата 3') as HTMLSelectElement).options].map(o=>o.value);
  expect(options).toContain('2');expect(options).not.toContain('4');
  fireEvent.change(screen.getByLabelText('Объединить кандидата 3'),{target:{value:'2'}});
  expect(within(home).getByText('2 фрагмента')).toBeInTheDocument();
 });

 it('flags one player given to two candidates that are on the pitch together',()=>{
  const groups=baseGroups(run);const candidates=candidatesOf(run,groups);
  const both=assignGroup(assignGroup([],[1,2,3],'p7'),[4],'p7');
  expect([...clashes(run,candidates,both).keys()].sort()).toEqual(['1-2-3','4']);
  expect(clashes(run,candidates,assignGroup([],[1,2,3],'p7')).size).toBe(0);
 });

 it('keeps the per-fragment queue for versions without track groups',()=>{
  render(<MemoryRouter><IdentityReview run={{...run,groups:[]} as unknown as AnalysisRun} actorId="admin" editable onSave={vi.fn()}/></MemoryRouter>);
  expect(screen.getByRole('button',{name:/По фрагментам/})).toHaveAttribute('aria-pressed','true');
  expect(screen.getByRole('navigation',{name:'Очередь треков'})).toBeInTheDocument();
 });
});
