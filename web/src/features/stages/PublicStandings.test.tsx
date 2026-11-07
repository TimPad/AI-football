import {afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,within} from '@testing-library/react';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {PublicTournamentPage} from '../public/PublicPages';
import {group,groupsStage,pair,side} from './fixtures.test-data';

const tournament={id:'t1',name:'Кубок Ярославля',season:'2026',starts_on:'2026-10-01',ends_on:'2026-12-31',timezone:'Europe/Moscow',standings_public:true};
function stub(stages:unknown[],fixtures:unknown[]=[],implicit=false){
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{const path=String(input);const page=(items:unknown[])=>({items,total:items.length});
  const body=path.includes('/standings')?{implicit,stages}:path.includes('/fixtures')?page(fixtures):path.includes('/matches')?page([]):tournament;
  return new Response(JSON.stringify(body))}));
}
const view=(path='/watch/tournaments/t1')=>render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/watch/tournaments/:id" element={<PublicTournamentPage/>}/></Routes></MemoryRouter>);
afterEach(()=>vi.unstubAllGlobals());

describe('раздел «Таблица» у зрителя',()=>{
 it('открывается первым, когда у турнира есть таблица',async()=>{
  stub([{...groupsStage,status:'drawn',groups:[group],sections:[{key:'rounds',name:'Туры',rounds:[],current_round:null}]}]);view();
  expect(await screen.findByRole('region',{name:'Группа A'})).toBeInTheDocument();
  const nav=screen.getByRole('navigation',{name:'Разделы турнира'});
  expect(within(nav).getAllByRole('link').map(a=>a.textContent)).toEqual(['Таблица','Матчи','Команды','Рейтинги']);
 });
 it('без таблицы открывает матчи и показывает пары без даты',async()=>{
  const fixture={id:'f1',stage_id:'s1',stage_name:'Плей-офф',key:'U1-1',leg:1,round_no:1,group_no:null,bracket:'upper',label:'Полуфинал',
   home:side('A1',false),away:side('B2',false),match_id:null,can_schedule:false};
  stub([],[fixture]);view();
  const block=await screen.findByRole('region',{name:'Ещё без даты'});
  expect(within(block).getByText('A1 — B2')).toBeInTheDocument();
  expect(within(block).queryByRole('button')).not.toBeInTheDocument();
  expect(within(screen.getByRole('navigation',{name:'Разделы турнира'})).queryByText('Таблица')).not.toBeInTheDocument();
 });
 it('показывает сетку плей-офф',async()=>{
  const playoff={...groupsStage,kind:'single_elim',name:'Плей-офф',status:'drawn',groups:[],sections:[{key:'upper',name:'Сетка',current_round:1,rounds:[{round_no:1,name:'Финал',pairs:[pair('U1-1','Финал',side('A1',false),side('B1',false))]}]}]};
  stub([playoff]);view();
  expect(await screen.findByRole('tab',{name:'Финал'})).toBeInTheDocument();
  expect(screen.getByRole('article',{name:/^Финал\. A1 — B1/})).toHaveTextContent('Дата не назначена');
 });
 it('турнир без формата открывается на матчах, общая таблица — отдельный раздел',async()=>{
  stub([{...groupsStage,name:'Турнирная таблица',kind:'round_robin',status:'started',groups:[{...group,name:'Турнирная таблица'}],sections:[]}],[],true);view();
  const nav=await screen.findByRole('navigation',{name:'Разделы турнира'});
  expect(within(nav).getByRole('link',{name:'Матчи'})).toHaveAttribute('aria-current','page');
  expect(within(nav).getByRole('link',{name:'Таблица'})).toBeInTheDocument();
 });
 it('ссылка с фильтром дня ведёт на матчи даже при формате',async()=>{
  stub([{...groupsStage,status:'drawn',groups:[group],sections:[]}]);view('/watch/tournaments/t1?day=2026-11-01');
  const nav=await screen.findByRole('navigation',{name:'Разделы турнира'});
  expect(within(nav).getByRole('link',{name:'Матчи'})).toHaveAttribute('aria-current','page');
 });
});
