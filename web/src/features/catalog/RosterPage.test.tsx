import {test,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,within} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {RosterPage} from './RosterPage';
vi.mock('../auth/Auth',()=>({useAuth:()=>({session:{id:'admin'}})}));
afterEach(()=>{vi.unstubAllGlobals();localStorage.clear()});
test('starts with selected roster, searches the catalogue, and adds a new player without leaving it',async()=>{
 const player={id:'p1',name:'Иван',archived:false};const other={id:'p2',name:'Андрей',archived:false};
 vi.stubGlobal('fetch',vi.fn(async input=>new Response(JSON.stringify(String(input).includes('/entries/')?{id:'entry',team_id:'team',revision:0,team:{name:'Север'},players:[{player_id:'p1',shirt_number:'7',player}]}:String(input).includes('/players')?{items:[player,other],total:2}:String(input).includes('/teams/')?{id:'team',players:[{player_id:'p2',shirt_number:'8',player:other}]}:{id:'tour',archived:false}))));
 render(<MemoryRouter initialEntries={['/tournaments/tour/teams/entry']}><Routes><Route path="/tournaments/:id/teams/:entryId" element={<RosterPage/>}/></Routes></MemoryRouter>);
 const current=await screen.findByRole('region',{name:'Текущая заявка'});expect(within(current).getByText('Иван')).toBeInTheDocument();expect(within(current).queryByText('Андрей')).toBeNull();fireEvent.change(screen.getByLabelText('Поиск игрока'),{target:{value:'Андрей'}});fireEvent.click(screen.getByRole('button',{name:'Добавить Андрей'}));expect(within(current).getByText('Андрей')).toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'Новый игрок в заявке'}));fireEvent.change(screen.getByLabelText('ФИО нового игрока'),{target:{value:'Новый человек'}});expect(within(current).getByDisplayValue('Новый человек')).toBeInTheDocument();expect(screen.getByLabelText('Номер Иван')).toHaveValue('7');
});
