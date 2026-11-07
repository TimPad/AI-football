import {afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {RosterPanel} from './RosterPanel';
import {WithdrawDialog} from './WithdrawDialog';
import {groupsStage,team} from './fixtures.test-data';
import type {Entry} from '../../api/domain';

const names=['Север','Юг','Запад','Восток','Луч'];
const entries=names.map(n=>({id:`e-${n}`,team_id:`t-${n}`,team:{id:`t-${n}`,name:n}})) as unknown as Entry[];
const drawn={...groupsStage,status:'drawn' as const,revision:3,draw:{id:'d',version:1,method:'pots',seed:1,seeding:[],participants:['e-Север','e-Юг','e-Запад','e-Восток'],
 placement:[['e-Север','e-Запад'],['e-Юг','e-Восток']],confirmed_at:''}};
type Sent={path:string,body:any};
function capture(respond:(path:string)=>unknown){
 const sent:Sent[]=[];
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{const path=String(input);sent.push({path,body:init?.body?JSON.parse(String(init.body)):null});
  const v=respond(path);return v instanceof Response?v:new Response(JSON.stringify(v??{}))}));
 return sent;
}
afterEach(()=>vi.unstubAllGlobals());

describe('состав этапа',()=>{
 it('убирает команду после предпросмотра последствий',async()=>{
  const sent=capture(p=>p.includes('/adjust/preview')?{method:'manual',seed:1,seeding:[],placement:[],groups:[],pairs:[],pots:{},kept:2,cancelled:1,error:null}:{implicit:false,stages:[]});
  const saved=vi.fn();
  render(<RosterPanel stage={drawn} entries={entries} onSaved={saved}/>);
  const groupA=screen.getByRole('heading',{name:'Группа A'}).nextElementSibling as HTMLElement;
  await userEvent.click(within(groupA).getAllByRole('button',{name:'Убрать'})[0]);
  const dialog=await screen.findByRole('dialog',{name:'Убрать Север из этапа'});
  expect(dialog).toHaveTextContent('Сохранятся 2 назначенных матча, 1 будут отменены.');
  expect(sent[0].body).toMatchObject({op:'remove',entry_id:'e-Север',expected_revision:3});
  await userEvent.click(within(dialog).getByRole('button',{name:'Применить'}));
  await waitFor(()=>expect(saved).toHaveBeenCalled());
  expect(sent[1].path).toMatch(/\/draw\/adjust$/);
 });
 it('без свободного места в сетке объясняет, что делать',async()=>{
  capture(()=>new Response(JSON.stringify({error:{code:'no_free_slot',message:'x',fields:{},current_revision:null}}),{status:409}));
  const bracket={...drawn,kind:'single_elim' as const,draw:{...drawn.draw,placement:[{entry:'e-Север'},{entry:'e-Юг'}]}};
  render(<RosterPanel stage={bracket} entries={entries} onSaved={vi.fn()}/>);
  await userEvent.selectOptions(screen.getByLabelText('Добавить команду'),'e-Луч');
  await userEvent.click(screen.getByRole('button',{name:'Добавить'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Свободных мест нет. Проведите жеребьёвку заново');
 });
 it('отмена не отправляет правку',async()=>{
  const sent=capture(()=>({method:'manual',seed:1,seeding:[],placement:[],groups:[],pairs:[],pots:{},kept:0,cancelled:0,error:null}));
  render(<RosterPanel stage={drawn} entries={entries} onSaved={vi.fn()}/>);
  await userEvent.selectOptions(screen.getByLabelText('Перенести Север в группу'),'2');
  const dialog=await screen.findByRole('dialog',{name:'Перенести Север в группу B'});
  expect(dialog).toHaveTextContent('Назначенные матчи не затронуты.');
  await userEvent.click(within(dialog).getByRole('button',{name:'Отмена'}));
  expect(sent).toHaveLength(1);
 });
});

describe('снятие команды',()=>{
 const preview=(rule:string)=>({entry_id:'e-Север',rule,default_rule:'annul',played:2,total:5,annulled:rule==='annul'?5:0,walkovers:rule==='walkover'?3:0,cancelled_matches:1});
 it('показывает правило по умолчанию, позволяет выбрать другое и подтверждает',async()=>{
  // Предпросмотр отвечает тем правилом, которое прислали (по умолчанию — аннулирование).
  const sent:Sent[]=[];
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{const path=String(input);const body=JSON.parse(String(init!.body));sent.push({path,body});
   return new Response(JSON.stringify(path.includes('/preview')?preview(body.rule??'annul'):{implicit:false,stages:[]}))}));
  const done=vi.fn();
  render(<WithdrawDialog stage={{...drawn,status:'started'}} teams={[team('Север'),team('Юг')]} onClose={vi.fn()} onDone={done}/>);
  await userEvent.selectOptions(screen.getByLabelText('Команда'),'e-Север');
  expect(await screen.findByRole('status')).toHaveTextContent('Сыграно 2 из 5. Результаты команды будут аннулированы, её не будет в таблице. 1 назначенный матч будет отменён.');
  await userEvent.click(screen.getByRole('button',{name:'Технические поражения'}));
  expect(await screen.findByText(/3 оставшихся будут засчитаны соперникам/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button',{name:'Снять команду'}));
  await waitFor(()=>expect(done).toHaveBeenCalled());
  expect(sent.at(-1)!.body).toMatchObject({entry_id:'e-Север',rule:'walkover',expected_revision:3});
 });
 it('отмена закрывает без отправки',async()=>{
  const sent=capture(()=>preview('annul'));const close=vi.fn();
  render(<WithdrawDialog stage={{...drawn,status:'started'}} teams={[team('Север')]} onClose={close} onDone={vi.fn()}/>);
  await userEvent.click(screen.getByRole('button',{name:'Отмена'}));
  expect(close).toHaveBeenCalled();expect(sent).toHaveLength(0);
 });
});
