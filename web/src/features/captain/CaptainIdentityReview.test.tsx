import {test,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {CaptainIdentityReview} from './CaptainIdentityReview';
vi.mock('./CaptainAuth',()=>({useCaptainAuth:()=>({session:{id:'captain'}})}));
afterEach(()=>{vi.unstubAllGlobals();localStorage.clear()});
test('one snapshot player is chosen for the whole group, saved, and independently confirmed',async()=>{
 let task={id:'task',team_id:'home',run_id:'run',match_id:'match',team_name:'Север',opponent_name:'Юг',side:'home',scheduled_at:'2026-10-20T16:00:00Z',status:'open',revision:0,expires_at:'2030-01-01T00:00:00Z',reason:'',groups:[{id:'1,2',tracks:[{track_id:1,intervals:[[0,60]],has_thumbnail:false},{track_id:2,intervals:[[65,120]],has_thumbnail:false}]}],players:[{player_id:'p1',display_name:'Иван',shirt_number:'7'}],draft:[] as unknown[]};const sent:Record<string,unknown>[]=[];
 vi.stubGlobal('fetch',vi.fn(async(input,init)=>{if(init?.body){const body=JSON.parse(init.body);sent.push(body);task={...task,revision:task.revision+1,...(String(input).endsWith('/draft')?{draft:body.decisions}:{status:'team_confirmed'})}}return new Response(JSON.stringify(task))}));
 render(<MemoryRouter initialEntries={['/captain/identity-tasks/task']}><Routes><Route path="/captain/identity-tasks/:taskId" element={<CaptainIdentityReview/>}/></Routes></MemoryRouter>);
 await screen.findAllByText('Кадр отсутствует');expect(screen.getByText('Определено 0 из 1')).toBeInTheDocument();fireEvent.change(screen.getByLabelText('Игрок группы 1,2'),{target:{value:'p1'}});expect(screen.getByRole('button',{name:'Подтвердить игроков своей команды'})).toBeDisabled();fireEvent.click(screen.getByRole('button',{name:'Сохранить решения'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Подтвердить игроков своей команды'})).toBeEnabled());expect(sent[0].decisions).toEqual([{group_id:'1,2',kind:'player',player_id:'p1',reason:''}]);fireEvent.click(screen.getByRole('button',{name:'Подтвердить игроков своей команды'}));await screen.findByText('Команда подтверждена самостоятельно');expect(sent).toHaveLength(2);
});

test('explicit unknown stays in a local draft after reload and a conflicting save preserves its reason',async()=>{
 const task={id:'task',team_name:'Север',opponent_name:'Юг',status:'open',revision:3,scheduled_at:'2026-10-20T16:00:00Z',groups:[{id:'1',tracks:[{track_id:1,intervals:[[0,60]],has_thumbnail:false}]}],players:[{player_id:'p1',display_name:'Иван',shirt_number:'7'}],draft:[]};
 vi.stubGlobal('fetch',vi.fn(async(_input,init)=>init?.body?new Response(JSON.stringify({error:{code:'revision_conflict',message:'Черновик изменён'}}),{status:409}):new Response(JSON.stringify(task))));
 const view=()=> <MemoryRouter initialEntries={['/captain/identity-tasks/task']}><Routes><Route path="/captain/identity-tasks/:taskId" element={<CaptainIdentityReview/>}/></Routes></MemoryRouter>;
 const first=render(view());await screen.findByLabelText('Игрок группы 1');fireEvent.change(screen.getByLabelText('Игрок группы 1'),{target:{value:'unknown'}});fireEvent.change(screen.getByLabelText('Причина решения группы 1'),{target:{value:'Игрока нет в списке'}});first.unmount();render(view());await screen.findByDisplayValue('Игрока нет в списке');expect(screen.getByText('Не определено явно: 1')).toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'Сохранить решения'}));await screen.findByText('Ввод сохранён на этом устройстве. Обновите данные и сравните их перед повтором.');expect(screen.getByDisplayValue('Игрока нет в списке')).toBeInTheDocument();expect(screen.getByRole('button',{name:'Подтвердить игроков своей команды'})).toBeDisabled();
});
