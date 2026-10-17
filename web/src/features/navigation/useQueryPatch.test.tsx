import {expect,it} from 'vitest';
import {fireEvent,render,screen} from '@testing-library/react';
import {MemoryRouter,useLocation} from 'react-router-dom';
import {useQueryPatch} from './useQueryPatch';

let search='';
let state:unknown;
function Filters(){
 const [,update]=useQueryPatch();search=useLocation().search;state=useLocation().state;
 return <button onClick={()=>{update({view:'grid'},{replace:true});update({day:'2026-10-20'},{replace:true})}}>оба</button>;
}
it('keeps both URL changes made before the next render',()=>{
 render(<MemoryRouter initialEntries={['/t?tab=matches']}><Filters/></MemoryRouter>);
 fireEvent.click(screen.getByRole('button',{name:'оба'}));
 const params=new URLSearchParams(search);
 expect([params.get('tab'),params.get('view'),params.get('day')]).toEqual(['matches','grid','2026-10-20']);
});
it('retains the schedule return state while switching tasks',()=>{
 const scheduleReturn='/tournaments/t?tab=matches&day=2026-10-20';
 render(<MemoryRouter initialEntries={[{pathname:'/m',search:'?tab=review',state:{scheduleReturn}}]}><Filters/></MemoryRouter>);
 fireEvent.click(screen.getByRole('button',{name:'оба'}));expect(state).toEqual({scheduleReturn});
});
