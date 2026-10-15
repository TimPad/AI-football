import {expect,it} from 'vitest';
import {fireEvent,render,screen} from '@testing-library/react';
import {MemoryRouter,useLocation} from 'react-router-dom';
import {useQueryPatch} from './useQueryPatch';

let search='';
function Filters(){
 const [,update]=useQueryPatch();search=useLocation().search;
 return <button onClick={()=>{update({view:'grid'},{replace:true});update({day:'2026-10-20'},{replace:true})}}>оба</button>;
}
it('keeps both URL changes made before the next render',()=>{
 render(<MemoryRouter initialEntries={['/t?tab=matches']}><Filters/></MemoryRouter>);
 fireEvent.click(screen.getByRole('button',{name:'оба'}));
 const params=new URLSearchParams(search);
 expect([params.get('tab'),params.get('view'),params.get('day')]).toEqual(['matches','grid','2026-10-20']);
});
