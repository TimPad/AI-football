import {afterEach,expect,it,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import {AuthProvider,Private,useAuth} from './Auth';

let state:unknown='unset';
function LoginProbe(){state=useLocation().state;return <p>Вход</p>}
function Page(){const {logout}=useAuth();return <button onClick={()=>void logout()}>Выйти</button>}
afterEach(()=>vi.unstubAllGlobals());

function app(){
 return render(<MemoryRouter initialEntries={['/matches/m1']}><AuthProvider><Routes><Route path="/login" element={<LoginProbe/>}/>
  <Route path="/matches/:id" element={<Private><Page/></Private>}/></Routes></AuthProvider></MemoryRouter>);
}

it('an explicit logout does not keep the previous page for the next login',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>String(input).endsWith('/auth/me')
  ?new Response(JSON.stringify({id:'a',login:'x',csrf_token:'t',can_manage_analytics:false}),{status:200})
  :new Response('{}',{status:200})));
 app();fireEvent.click(await screen.findByRole('button',{name:'Выйти'}));
 await screen.findByText('Вход');expect(state).toBeNull();
});

it('an expired session keeps the page to return to after login',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({error:{code:'auth',message:'Нет'}}),{status:401})));
 app();await screen.findByText('Вход');
 await waitFor(()=>expect(state).toEqual({from:'/matches/m1'}));
});
