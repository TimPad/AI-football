import {afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,within} from '@testing-library/react';
import {useState,type ReactNode} from 'react';
import {MemoryRouter} from 'react-router-dom';
import {RailContext} from '../navigation/rail';
import {TournamentWorkspace} from './TournamentWorkspace';
import preset from '../../test/preset.json';

const auth=vi.hoisted(()=>({analytics:false}));
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
   :path.includes(`/tournaments/${T}/matches`)?page([match]):page([]);
  return new Response(JSON.stringify(body));
 }));
 return paths;
}
function Harness({tab}:{tab:string}){
 const [rail,setRail]=useState<ReactNode>(null);
 return <MemoryRouter initialEntries={[`/tournaments/${T}?tab=${tab}`]}><nav aria-label="Рейл">{rail}</nav>
  <RailContext.Provider value={setRail}><TournamentWorkspace tournamentId={T}/></RailContext.Provider></MemoryRouter>;
}
afterEach(()=>{vi.unstubAllGlobals();auth.analytics=false});

describe('tournament workspace',()=>{
 it('groups tournament navigation and keeps the calendar in cabinet links',async()=>{
  stub();render(<Harness tab="matches"/>);
  expect(await screen.findByRole('heading',{name:'Матчи'})).toBeInTheDocument();
  const rail=screen.getByRole('navigation',{name:'Рейл'});
  expect(await within(rail).findByText('Работа')).toBeInTheDocument();
  for(const group of ['Участники и площадки','Настройки'])expect(within(rail).getByText(group)).toBeInTheDocument();
  expect(within(rail).getByRole('link',{name:'Матчи'})).toHaveAttribute('aria-current','page');
  expect(within(rail).queryByRole('link',{name:'Рейтинги'})).toBeNull();
  expect(screen.getByRole('link',{name:'Открыть матч Север — Юг'})).toHaveAttribute('href','/matches/m1');
 });
 it('shows players from tournament entries and links to the existing roster editor',async()=>{
  const paths=stub();render(<Harness tab="players"/>);
  expect(await screen.findByText('Иван Петров')).toBeInTheDocument();
  expect(screen.getByText('Пётр Иванов')).toBeInTheDocument();
  expect(screen.getAllByRole('link',{name:'Изменить заявку →'})[0]).toHaveAttribute('href',`/tournaments/${T}/teams/e-a`);
  expect(paths.some(p=>p.includes('/api/v1/players'))).toBe(false);
 });
 it('lists halls from the schedule and opens the shared hall editor',async()=>{
  stub();render(<Harness tab="halls"/>);
  expect(await screen.findByRole('link',{name:'Открыть зал →'})).toHaveAttribute('href','/halls/h1');
  expect(screen.getByText('Спортивная, 1')).toBeInTheDocument();
 });
 it('keeps old tabs and shows ratings only to Admin+',async()=>{
  stub();const {unmount}=render(<Harness tab="teams"/>);
  expect(await screen.findByRole('heading',{name:'Команды турнира'})).toBeInTheDocument();unmount();
  render(<Harness tab="rules"/>);
  expect(await screen.findByRole('heading',{name:'Регламент турнира'})).toBeInTheDocument();
 });
 it('summarises publication readiness without per-match version requests',async()=>{
  const paths=stub();render(<Harness tab="publication"/>);
  expect(await screen.findByText('Не опубликован')).toBeInTheDocument();
  expect(screen.getByText('Откройте матч для проверки')).toBeInTheDocument();
  expect(paths.some(p=>/\/matches\/m1\/(versions|analysis|ratings)/.test(p))).toBe(false);
 });
});
