import {it,expect,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {TeamEditor} from './TeamEditor';
vi.mock('../auth/Auth',()=>({useAuth:()=>({session:{id:'test-admin'}})}));

it('creates player rows in the team form and retains a draft on remount',()=>{
 localStorage.clear();
 const props={existing:undefined,players:[],onSaved:vi.fn()};
 const view=render(<MemoryRouter><TeamEditor {...props}/></MemoryRouter>);
 expect(screen.getByLabelText('ФИО игрока 1')).toBeVisible();
 fireEvent.change(screen.getByLabelText('Название команды'),{target:{value:'Север'}});
 fireEvent.click(screen.getByRole('button',{name:'Добавить строку игрока'}));
 fireEvent.change(screen.getByLabelText('ФИО игрока 1'),{target:{value:'Иван Петров'}});
 fireEvent.change(screen.getByLabelText('Номер игрока 1'),{target:{value:'7'}});
 view.unmount();
 render(<MemoryRouter><TeamEditor {...props}/></MemoryRouter>);
 expect(screen.getByLabelText('Название команды')).toHaveValue('Север');
 expect(screen.getByLabelText('ФИО игрока 1')).toHaveValue('Иван Петров');
 expect(screen.getByLabelText('Номер игрока 1')).toHaveValue('7');
 expect(screen.getByText('Черновик восстановлен')).toBeVisible();
 localStorage.clear();
});
