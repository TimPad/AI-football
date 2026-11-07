import {afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,within} from '@testing-library/react';
import {useState,type ReactNode} from 'react';
import {MemoryRouter} from 'react-router-dom';
import {RailContext} from '../navigation/rail';
import {TournamentWorkspace} from './TournamentWorkspace';
import preset from '../../test/preset.json';

const auth=vi.hoisted(()=>({analytics:false}));
const fixtures=vi.hoisted(()=>({list:[] as unknown[]}));
vi.mock('../auth/Auth',()=>({useAuth:()=>({session:{id:'admin',can_manage_analytics:auth.analytics}})}));
const T='t1';
const hall={id:'h1',name:'Зал 1',address:'Спортивная, 1',pitch_length_m:41,pitch_width_m:15.5};
const regulation={rules:{schedule_slot_s:5400}};
const team=(id:string,name:string)=>({id:`e-${id}`,team_id:id,team:{id,name}});
const match={id:'m1',scheduled_at:'2026-10-20T15:00:00Z',venue_label:'Зал 1',hall_snapshot:hall,status:'ended',regulation,regulation_override:null,
 home:team('a','Север'),away:team('b','Юг'),projection:{effective_score:{home:3,away:2}},broadcast_url:null,broadcast_embed_url:null,published_version_id:null};
const roster=(id:string,name:string,player:string)=>({id:`e-${id}`,team:{id,name},players:[{id:`rp-${id}`,player_id:`p-${id}`,shirt_number:'7',active:true,player:{name:player,position:'ala'}}]});

function stub(){
 const paths:string[]=[];
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{
  const path=String(input);paths.push(path);
  const page=(items:unknown[])=>({items,total:items.length});
  const body=path.endsWith(`/tournaments/${T}`)?{id:T,name:'Кубок Ярославля',season:'2026',timezone:'Europe/Moscow',archived:false,revision:1}
   :path.includes('/entries/e-a/players')?roster('a','Север','Иван Петров'):path.includes('/entries/e-b/players')?roster('b','Юг','Пётр Иванов')
   :path.includes(`/tournaments/${T}/entries`)?page([team('a','Север'),team('b','Юг')])
   :path.includes('/regulation-presets')?{items:[{name:'Футзал',rules:preset}]}
   :path.includes('/regulations')?page([{id:'r1',variant_name:'Основной',version:1,rules:preset}])
   :path.includes(`/tournaments/${T}/matches`)?page([match])
   :path.includes(`/tournaments/${T}/fixtures`)?page(fixtures.list):page([]);
  return new Response(JSON.stringify(body));
 }));
 return paths;
}
function Harness({tab}:{tab:string}){
 const [rail,setRail]=useState<ReactNode>(null);
 return <MemoryRouter initialEntries={[`/tournaments/${T}?tab=${tab}`]}><nav aria-label="Рейл">{rail}</nav>
  <RailContext.Provider value={setRail}><TournamentWorkspace tournamentId={T}/></RailContext.Provider></MemoryRouter>;
}
afterEach(()=>{vi.unstubAllGlobals();auth.analytics=false;fixtures.list=[]});
const side=(label:string,known=true)=>({label,team:known?{entry_id:`e-${label}`,team_id:label,name:label}:null});
const fixture=(id:string,home:ReturnType<typeof side>,away:ReturnType<typeof side>,can:boolean)=>({id,stage_id:'s1',stage_name:'Групповой этап',key:id,leg:1,round_no:1,group_no:1,bracket:null,label:'Группа A · Тур 1',home,away,match_id:null,can_schedule:can});

describe('tournament workspace',()=>{
 it('shows tournament sections and keeps the calendar in cabinet links',async()=>{
  stub();render(<Harness tab="matches"/>);
  expect(await screen.findByRole('heading',{name:'Матчи'})).toBeInTheDocument();
  const rail=screen.getByRole('navigation',{name:'Рейл'});
  await within(rail).findByRole('link',{name:'Матчи'});
  expect(within(rail).getAllByRole('link').map(a=>a.textContent)).toEqual(['Кубок Ярославля','Таблица','Матчи','Команды','Настройки']);
  expect(within(rail).getByRole('link',{name:'Матчи'})).toHaveAttribute('aria-current','page');
  expect(screen.getByRole('link',{name:'Открыть матч Север — Юг'})).toHaveAttribute('href','/matches/m1');
 });
 it('marks an ended match that is not on the site yet, without per-match requests',async()=>{
  const paths=stub();render(<Harness tab="matches"/>);
  expect(await screen.findByText('Не на сайте')).toBeInTheDocument();
  expect(paths.some(p=>/\/matches\/m1\/(versions|analysis|ratings)/.test(p))).toBe(false);
 });
 it('opens old section links in the sections that replaced them',async()=>{
  stub();let view=render(<Harness tab="players"/>);
  expect(await screen.findByRole('heading',{name:'Команды турнира'})).toBeInTheDocument();view.unmount();
  view=render(<Harness tab="publication"/>);
  expect(await screen.findByText('Не на сайте')).toBeInTheDocument();view.unmount();
  render(<Harness tab="halls"/>);
  expect(await screen.findByRole('heading',{name:'Матчи'})).toBeInTheDocument();
 });
 it('keeps regulation and tournament details under settings; ratings only for Admin+',async()=>{
  stub();const {unmount}=render(<Harness tab="rules"/>);
  expect(await screen.findByRole('heading',{name:'Регламент турнира'})).toBeInTheDocument();
  const rail=screen.getByRole('navigation',{name:'Рейл'});
  expect(await within(rail).findByRole('link',{name:'Настройки'})).toHaveAttribute('aria-current','page');
  const settings=screen.getByRole('navigation',{name:'Настройки турнира'});
  expect(within(settings).getByRole('link',{name:'Сведения о турнире'})).toHaveAttribute('href','?tab=info');
  unmount();auth.analytics=true;render(<Harness tab="info"/>);
  expect(await screen.findByRole('heading',{name:'Сведения о турнире'})).toBeInTheDocument();
  expect(await within(screen.getByRole('navigation',{name:'Рейл'})).findByRole('link',{name:'Рейтинги'})).toBeInTheDocument();
 });
 it('lists pairs without a date with a schedule button',async()=>{
  fixtures.list=[fixture('f1',side('Север'),side('Юг'),true),fixture('f2',side('Победитель пары 1',false),side('B2',false),false)];
  stub();render(<Harness tab="matches"/>);
  const block=await screen.findByRole('region',{name:'Без даты'});
  expect(within(block).getByText('Север — Юг')).toBeInTheDocument();
  expect(within(block).getAllByRole('button',{name:'Назначить'})).toHaveLength(1);
  expect(within(block).getByText('Соперник ещё не известен')).toBeInTheDocument();
 });
});
