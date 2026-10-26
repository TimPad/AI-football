import {afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {StageWorkspace} from './StageWorkspace';
import {groupsStage} from './fixtures.test-data';
import type {Entry,RegVersion,Tournament} from '../../api/domain';

afterEach(()=>vi.unstubAllGlobals());
describe('вкладка «Таблица» кабинета',()=>{
 it('меняет порядок критериев до жеребьёвки',async()=>{
  const sent:{method?:string,body:any}[]=[];
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{if(init?.method)sent.push({method:init.method,body:JSON.parse(String(init.body))});
   return new Response(JSON.stringify(String(input).includes('/stages')&&!init?.method?{implicit:false,stages:[{...groupsStage,criteria:['points','h2h_points','goal_diff','lot']}]}:{implicit:false,stages:[]}))}));
  render(<MemoryRouter><StageWorkspace tournament={{id:'t1',timezone:'Europe/Moscow'} as Tournament} entries={[] as Entry[]} regulations={[{id:'r1'}] as RegVersion[]}/></MemoryRouter>);
  const editor=await screen.findByText('Порядок мест при равенстве очков');await userEvent.click(editor);
  const list=editor.closest('details')!;
  expect(within(list).getByRole('button',{name:'очки выше'})).toBeDisabled();
  await userEvent.click(within(list).getByRole('button',{name:'разница мячей выше'}));
  await userEvent.click(within(list).getByRole('button',{name:'Сохранить порядок'}));
  await waitFor(()=>expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({method:'PATCH',body:{expected_revision:0,config:{criteria:['points','goal_diff','h2h_points','lot']}}});
 });
});
