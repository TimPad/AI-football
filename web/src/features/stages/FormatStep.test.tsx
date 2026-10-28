import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {FormatStep} from './FormatStep';
import {DrawStep} from './DrawStep';
import {groupsStage,team} from './fixtures.test-data';
import type {RegVersion,Entry} from '../../api/domain';

const reg={id:'r1',variant_name:'Основной',version:1} as RegVersion;
const names=['Север','Юг','Запад','Восток'];
const entries=names.map(n=>({id:`e-${n}`,team_id:`t-${n}`,team:{id:`t-${n}`,name:n}})) as unknown as Entry[];
const card=(template:string,extra:Record<string,unknown>={})=>({template,params:{},summary:'',matches:12,per_team:[3,5],rounds:5,days:5,fits:null,warnings:[],fix:null,recommended:false,reason:null,...extra});
const cards=(extra:Record<string,Record<string,unknown>>={})=>({teams:4,cards:['league','groups_playoff','playoff','double_elim','swiss'].map(t=>card(t,extra[t]))});
type Sent={path:string,method:string,body:any};
function capture(respond:(path:string,body:any)=>unknown){
 const sent:Sent[]=[];
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{const path=String(input);const body=init?.body?JSON.parse(String(init.body)):null;sent.push({path,method:init?.method??'GET',body});
  const value=respond(path,body);return value instanceof Response?value:new Response(JSON.stringify(value??{}))}));
 return sent;
}
const estimates=(sent:Sent[])=>sent.filter(s=>s.path.includes('/format/estimate'));
beforeEach(()=>{try{localStorage.clear()}catch{/* пусто */}});
afterEach(()=>vi.unstubAllGlobals());

describe('подсказки формата',()=>{
 it('показывает рекомендацию с объяснением, факты и подставляет автоподбор',async()=>{
  capture(p=>p.includes('/estimate')?cards({groups_playoff:{recommended:true,reason:'Каждая команда сыграет минимум 3 матча за 5 игровых дней',params:{group_count:3,per_group:2,best_thirds:2}}}):{});
  render(<FormatStep tid="t1" regulations={[reg]} standings={{implicit:false,stages:[]}} entries={entries} onSaved={vi.fn()}/>);
  const chosen=screen.getByRole('radio',{name:/Группы и плей-офф/});
  expect(await within(chosen).findByText('Рекомендуем')).toBeInTheDocument();
  expect(within(chosen).getByText('Каждая команда сыграет минимум 3 матча за 5 игровых дней')).toBeInTheDocument();
  expect(within(chosen).getByText('12 матчей · 3–5 на команду · 5 игровых дней')).toBeInTheDocument();
  expect(screen.getByRole('group',{name:'Групп'})).toHaveTextContent('3');
  expect(screen.getByText(/Команд:/)).toHaveTextContent('Команд: 4');
 });
 it('степпер пересчитывает подсказку, исправление меняет число групп',async()=>{
  const sent=capture(p=>p.includes('/estimate')?cards({groups_playoff:{warnings:['Для 4 групп нужно минимум 8 команд'],fix:{group_count:2}}}):{});
  render(<FormatStep tid="t1" regulations={[reg]} standings={{implicit:false,stages:[]}} entries={entries} onSaved={vi.fn()}/>);
  await waitFor(()=>expect(estimates(sent).length).toBeGreaterThan(0));
  await userEvent.click(screen.getByRole('button',{name:'Увеличить: Групп'}));
  await waitFor(()=>expect(estimates(sent).at(-1)!.body.params.group_count).toBe(3));
  expect(await screen.findByText('Для 4 групп нужно минимум 8 команд')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button',{name:'Сделать 2 группы'}));
  await waitFor(()=>expect(estimates(sent).at(-1)!.body.params.group_count).toBe(2));
 });
 it('степпер на минимуме сообщает предел, игровые дни можно не задавать',async()=>{
  const sent=capture(p=>p.includes('/estimate')?cards():{});
  render(<FormatStep tid="t1" regulations={[reg]} standings={{implicit:false,stages:[]}} entries={entries} onSaved={vi.fn()}/>);
  await userEvent.click(screen.getByRole('button',{name:'Уменьшить: Групп'}));
  expect(screen.getByRole('group',{name:'Групп'})).toHaveTextContent('Минимум 2');
  expect(screen.getByRole('group',{name:'Игровых дней'})).toHaveTextContent('Не задано');
  await userEvent.click(screen.getByRole('button',{name:'Увеличить: Игровых дней'}));
  await waitFor(()=>expect(estimates(sent).at(-1)!.body.days).toBe(1));
 });
 it('пояснение открывается и закрывается кнопкой «Готово»',async()=>{
  capture(()=>cards());
  render(<FormatStep tid="t1" regulations={[reg]} standings={{implicit:false,stages:[]}} entries={entries} onSaved={vi.fn()}/>);
  await userEvent.click(screen.getByRole('button',{name:'Как выбрать формат'}));
  const dialog=screen.getByRole('dialog',{name:'Как выбрать формат'});
  expect(within(dialog).getAllByRole('term')).toHaveLength(5);
  await userEvent.click(within(dialog).getByRole('button',{name:'Готово'}));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
 });
 it('«Кто играет» меняет число команд в расчёте и сохраняет формат',async()=>{
  const sent=capture(p=>p.includes('/estimate')?cards():{implicit:false,stages:[]});const saved=vi.fn();
  render(<FormatStep tid="t1" regulations={[reg]} standings={{implicit:false,stages:[]}} entries={entries} onSaved={saved}/>);
  await userEvent.click(screen.getByRole('button',{name:'Изменить'}));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('checkbox',{name:'Восток'}));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Готово'}));
  await waitFor(()=>expect(estimates(sent).at(-1)!.body.teams).toBe(3));
  await userEvent.click(screen.getByRole('button',{name:'Сохранить формат'}));
  await waitFor(()=>expect(saved).toHaveBeenCalled());
  expect(sent.find(s=>s.path.endsWith('/tournaments/t1/format'))!.body).toMatchObject({template:'groups_playoff',regulation_id:'r1'});
  expect(JSON.parse(localStorage.getItem('aifootball:participants:t1')!)).toEqual(['e-Север','e-Юг','e-Запад']);
 });
 it('после жеребьёвки формат закреплён',()=>{
  capture(()=>cards());
  render(<FormatStep tid="t1" regulations={[reg]} entries={entries} standings={{implicit:false,stages:[{...groupsStage,draw:{id:'d',version:1,method:'pots',seed:1,seeding:[],placement:[],participants:null,confirmed_at:''}}]}} onSaved={vi.fn()}/>);
  expect(screen.getByText('Формат закреплён жеребьёвкой.')).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:/(Сохранить|Заменить) формат/})).not.toBeInTheDocument();
 });
});

describe('жеребьёвка',()=>{
 const preview=(placement:string[][])=>({method:'pots',seed:1,seeding:entries.map(e=>e.id),placement,groups:placement.map(g=>g.map(id=>team(id.slice(2)))),pairs:[],pots:{'e-Север':1,'e-Юг':1,'e-Запад':2,'e-Восток':2},kept:0,cancelled:0,error:null});
 it('меняет две команды местами и подтверждает ручную жеребьёвку',async()=>{
  const sent=capture(p=>p.includes('/draw/preview')?preview([['e-Север','e-Запад'],['e-Юг','e-Восток']]):{implicit:false,stages:[]});const saved=vi.fn();
  render(<DrawStep stage={groupsStage} entries={entries} timezone="Europe/Moscow" tid="t1" onSaved={saved}/>);
  await userEvent.click(screen.getByRole('button',{name:'Провести жеребьёвку'}));
  expect(await screen.findByRole('heading',{name:'Группа A'})).toBeInTheDocument();
  expect(sent[0].body).toMatchObject({method:'pots',seeding:entries.map(e=>e.id),participants:entries.map(e=>e.id)});
  await userEvent.click(screen.getByRole('button',{name:'Север'}));
  await userEvent.click(screen.getByRole('button',{name:'Юг'}));
  await waitFor(()=>expect(sent).toHaveLength(2));
  expect(sent[1].body).toMatchObject({method:'manual',placement:[['e-Юг','e-Запад'],['e-Север','e-Восток']]});
  await userEvent.click(await screen.findByRole('button',{name:'Подтвердить жеребьёвку'}));
  await waitFor(()=>expect(saved).toHaveBeenCalled());
  expect(sent[2].path).toMatch(/\/stages\/s1\/draw$/);
  expect(sent[2].body).toMatchObject({expected_revision:0,seeding:entries.map(e=>e.id)});
 });
 it('двигает команду в посеве',async()=>{
  capture(()=>({}));
  render(<DrawStep stage={groupsStage} entries={entries} timezone="Europe/Moscow" tid="t1" onSaved={vi.fn()}/>);
  await userEvent.click(screen.getByRole('button',{name:'Юг выше'}));
  expect(within(screen.getByRole('list')).getAllByRole('listitem')[0]).toHaveTextContent('Юг');
 });
 it('без нужного числа команд предлагает «Сделать N групп»',async()=>{
  let patched=false;
  const sent=capture((p,body)=>{
   if(p.includes('/draw/preview')&&!patched)return new Response(JSON.stringify({error:{code:'not_enough_teams',message:'Для 4 групп нужно минимум 8 команд',fields:{group_count:'2'},current_revision:null}}),{status:422});
   if(p.endsWith('/stages/s1')){patched=true;return {implicit:false,stages:[{...groupsStage,revision:1,config:body.config}]}}
   return preview([['e-Север','e-Запад'],['e-Юг','e-Восток']]);
  });
  render(<DrawStep stage={{...groupsStage,config:{kind:'groups',group_count:4,source:{entries:'all'}}}} entries={entries} timezone="Europe/Moscow" tid="t1" onSaved={vi.fn()}/>);
  await userEvent.click(screen.getByRole('button',{name:'Провести жеребьёвку'}));
  await userEvent.click(await screen.findByRole('button',{name:'Сделать 2 группы'}));
  expect(await screen.findByRole('heading',{name:'Группа A'})).toBeInTheDocument();
  expect(sent.find(s=>s.method==='PATCH')!.body).toMatchObject({expected_revision:0,config:{group_count:2}});
 });
});
