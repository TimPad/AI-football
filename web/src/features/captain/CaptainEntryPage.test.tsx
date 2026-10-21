import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {CaptainEntryPage} from './CaptainEntryPage';
vi.mock('./CaptainAuth',()=>({useCaptainAuth:()=>({session:{id:'captain'}})}));
afterEach(()=>{vi.unstubAllGlobals();localStorage.clear()});
it('keeps the submitted version visible while draft edits require saving',async()=>{
 const payload={source_roster_revision:1,players:[{player_id:'p1',display_name:'Иван',shirt_number:'7'}]};
 const app={id:'a1',team_id:'t1',team_name:'Север',tournament_id:'tour',tournament:{id:'tour',name:'Кубок',season:'2026',applications_open:true,deadline:null},revision:2,status:'changes_requested',reason:'Уточнить номер',draft:payload,submitted_version:{id:'v1',number:1,payload},versions:[{id:'v1',number:1,payload}]};
 vi.stubGlobal('fetch',vi.fn(async input=>new Response(JSON.stringify(String(input).includes('/applications/')?app:{id:'t1',revision:1,archived:false,players:[{player_id:'p1',shirt_number:'7',player:{name:'Иван',archived:false}}]}))));
 render(<MemoryRouter initialEntries={['/captain/applications/a1']}><Routes><Route path="/captain/applications/:id" element={<CaptainEntryPage/>}/></Routes></MemoryRouter>);
 await screen.findByText('Уточнить номер');expect(screen.getByText('Отправленная версия №1')).toBeInTheDocument();fireEvent.change(screen.getByLabelText('Номер Иван'),{target:{value:'9'}});expect(screen.getByRole('button',{name:'Отправить заявку'})).toBeDisabled();expect(screen.getByText('Сначала сохраните изменения черновика')).toBeInTheDocument();expect(screen.getByText('№ 7')).toBeInTheDocument();
});
