import {afterEach,it,expect,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {TournamentCreate} from './TournamentSetup';
vi.mock('../auth/Auth',()=>({useAuth:()=>({session:{id:'admin'}})}));
afterEach(()=>{localStorage.clear();vi.unstubAllGlobals()});
function mount(){return render(<MemoryRouter initialEntries={['/tournaments/new']}><Routes><Route path="/tournaments/new" element={<TournamentCreate/>}/><Route path="/tournaments/:id" element={<h1>Обзор</h1>}/><Route path="/tournaments/:id/setup" element={<h1>Продолжение настройки</h1>}/></Routes></MemoryRouter>)}
function fill(){for(const [label,value] of [['Название турнира','Кубок'],['Начало турнира','2026-10-18'],['Окончание турнира','2026-11-18']])fireEvent.change(screen.getByLabelText(label),{target:{value}})}
it.each([['Создать турнир','Обзор'],['Создать и добавить команды','Продолжение настройки']])('supports %s without requiring a roster',async(button,destination)=>{
 const bodies:unknown[]=[];vi.stubGlobal('fetch',vi.fn(async(_input,init)=>{bodies.push(JSON.parse(init.body));return new Response(JSON.stringify({id:'t1'}))}));
 mount();fill();fireEvent.click(screen.getByRole('button',{name:button}));await screen.findByRole('heading',{name:destination});expect(bodies).toHaveLength(1);expect(bodies[0]).toMatchObject({name:'Кубок',visibility:'draft'});
});
it('restores input and replays identical creation after a lost response',async()=>{
 const bodies:string[]=[];vi.stubGlobal('fetch',vi.fn(async(_input,init)=>{bodies.push(init.body);if(bodies.length===1)throw Error('lost');return new Response(JSON.stringify({id:'t1'}))}));
 const view=mount();fill();fireEvent.click(screen.getByRole('button',{name:'Создать и добавить команды'}));await screen.findByRole('button',{name:'Повторить создание'});view.unmount();
 mount();expect(screen.getByLabelText('Название турнира')).toHaveValue('Кубок');fireEvent.click(screen.getByRole('button',{name:'Повторить создание'}));await screen.findByRole('heading',{name:'Продолжение настройки'});expect(bodies[1]).toBe(bodies[0]);
});
