import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {CaptainAuthProvider,CaptainLogin,CaptainRegister} from './CaptainAuth';
afterEach(()=>{vi.unstubAllGlobals();localStorage.clear()});
it('uses the separate captain session and preserves a task destination',async()=>{
 const paths:string[]=[];vi.stubGlobal('fetch',vi.fn(async(input,init)=>{paths.push(String(input));return init?.method==='POST'?new Response(JSON.stringify({id:'c',email:'c@example.test',display_name:'Капитан',csrf_token:'cap'})):new Response('{}',{status:401})}));
 render(<MemoryRouter initialEntries={[{pathname:'/captain/login',state:{from:'/captain/identity-tasks/t'}}]}><CaptainAuthProvider><Routes><Route path="/captain/login" element={<CaptainLogin/>}/><Route path="/captain/identity-tasks/t" element={<h1>Проверка команды</h1>}/></Routes></CaptainAuthProvider></MemoryRouter>);
 fireEvent.change(screen.getByLabelText('Email'),{target:{value:'c@example.test'}});fireEvent.change(screen.getByLabelText('Пароль'),{target:{value:'testing-captain-password'}});fireEvent.click(screen.getByRole('button',{name:'Войти'}));await screen.findByRole('heading',{name:'Проверка команды'});expect(paths).toContain('/api/v1/captain/auth/login');expect(paths).not.toContain('/api/v1/auth/login');
});
it('requires email confirmation instead of treating registration as a session',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(_input,init)=>init?.method==='POST'?new Response('{"message":"Письмо поставлено в очередь"}',{status:202}):new Response('{}',{status:401})));
 render(<MemoryRouter><CaptainAuthProvider><CaptainRegister/></CaptainAuthProvider></MemoryRouter>);
 fireEvent.change(screen.getByLabelText('Имя капитана'),{target:{value:'Иван'}});fireEvent.change(screen.getByLabelText('Email'),{target:{value:'c@example.test'}});fireEvent.change(screen.getByLabelText('Пароль'),{target:{value:'testing-captain-password'}});fireEvent.click(screen.getByRole('button',{name:'Зарегистрироваться'}));await screen.findByRole('heading',{name:'Проверьте почту'});expect(screen.queryByText('Создать команду')).not.toBeInTheDocument();
});
