import {it,expect,afterEach} from 'vitest';
import {useLayoutEffect} from 'react';
import {render,screen} from '@testing-library/react';
import {useDraft} from './drafts';
afterEach(()=>localStorage.clear());
it('keeps an edit made before the initial passive effect finishes',()=>{
 function Harness(){const d=useDraft('draft-race',{name:'С сервера'},(v:unknown):v is {name:string}=>!!v&&typeof v==='object'&&'name' in v);useLayoutEffect(()=>d.change({name:'Изменено пользователем'}),[]);return <output>{d.value.name}</output>}
 render(<Harness/>);expect(screen.getByRole('status')).toHaveTextContent('Изменено пользователем');
});
