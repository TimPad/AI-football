import {afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {FormatStep} from './FormatStep';
import {DrawStep} from './DrawStep';
import {groupsStage,team} from './fixtures.test-data';
import type {RegVersion,Entry} from '../../api/domain';

const reg={id:'r1',variant_name:'Основной',version:1} as RegVersion;
const entries=['Север','Юг','Запад','Восток'].map(n=>({id:`e-${n}`,team_id:`t-${n}`,team:{id:`t-${n}`,name:n}})) as unknown as Entry[];
function capture(responses:Record<string,unknown>){
 const sent:{path:string,body:any}[]=[];
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{const path=String(input);sent.push({path,body:init?.body?JSON.parse(String(init.body)):null});
  const key=Object.keys(responses).find(k=>path.includes(k));return new Response(JSON.stringify(key?responses[key]:{}))}));
 return sent;
}
afterEach(()=>vi.unstubAllGlobals());

describe('формат и жеребьёвка',()=>{
 it('сохраняет «Группы и плей-офф» с параметрами',async()=>{
  const sent=capture({'/format':{implicit:false,stages:[]}});const saved=vi.fn();
  render(<FormatStep tid="t1" regulations={[reg]} standings={{implicit:false,stages:[]}} onSaved={saved}/>);
  expect(screen.getByRole('radio',{name:/Группы и плей-офф/})).toHaveAttribute('aria-checked','true');
  await userEvent.clear(screen.getByLabelText('Групп'));await userEvent.type(screen.getByLabelText('Групп'),'4');
  await userEvent.click(screen.getByLabelText('Матч за 3-е место'));
  await userEvent.click(screen.getByRole('button',{name:'Сохранить формат'}));
  await waitFor(()=>expect(saved).toHaveBeenCalled());
  expect(sent[0].path).toContain('/tournaments/t1/format');
  expect(sent[0].body).toMatchObject({template:'groups_playoff',group_count:4,per_group:2,third_place:true,regulation_id:'r1'});
 });
 it('после жеребьёвки формат закреплён',()=>{
  render(<FormatStep tid="t1" regulations={[reg]} standings={{implicit:false,stages:[{...groupsStage,draw:{id:'d',version:1,method:'pots',seed:1,seeding:[],placement:[],confirmed_at:''}}]}} onSaved={vi.fn()}/>);
  expect(screen.getByText('Формат закреплён жеребьёвкой.')).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:/формат/})).not.toBeInTheDocument();
 });
 it('меняет две команды местами и подтверждает ручную жеребьёвку',async()=>{
  const preview=(placement:string[][])=>({method:'pots',seed:1,seeding:entries.map(e=>e.id),placement,groups:placement.map(g=>g.map(id=>team(id.slice(2)))),pairs:[],pots:{'e-Север':1,'e-Юг':1,'e-Запад':2,'e-Восток':2},kept:0,cancelled:0});
  const sent=capture({'/draw/preview':preview([['e-Север','e-Запад'],['e-Юг','e-Восток']]),'/draw':{implicit:false,stages:[]}});const saved=vi.fn();
  render(<DrawStep stage={groupsStage} entries={entries} timezone="Europe/Moscow" onSaved={saved}/>);
  await userEvent.click(screen.getByRole('button',{name:'Провести жеребьёвку'}));
  expect(await screen.findByRole('heading',{name:'Группа A'})).toBeInTheDocument();
  expect(sent[0].body).toMatchObject({method:'pots',seeding:entries.map(e=>e.id)});
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
  capture({});
  render(<DrawStep stage={groupsStage} entries={entries} timezone="Europe/Moscow" onSaved={vi.fn()}/>);
  await userEvent.click(screen.getByRole('button',{name:'Юг выше'}));
  expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('Юг');
 });
});
