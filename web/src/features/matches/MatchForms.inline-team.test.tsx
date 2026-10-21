import {test,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {MatchCreateForm} from './MatchForms';
import type {Tournament,Entry,RegVersion} from '../../api/domain';
vi.mock('../halls/HallSelection',()=>({HallSelection:()=>null}));
vi.mock('../../api/client',()=>({all:async()=>[],api:async()=>({id:'new-team'}),post:async()=>({id:'new-entry',team_id:'new-team',team:{name:'Новая'}})}));
vi.mock('../catalog/TeamEditor',()=>({TeamEditor:({onSubmit,onSaved}:{onSubmit:(v:unknown)=>Promise<unknown>,onSaved:(v:unknown)=>void})=><button type="button" onClick={async()=>onSaved(await onSubmit({request_id:'req',name:'Новая',players:[]}))}>Сохранить новую команду</button>}));
test('creating a home team in place preserves the opponent and match time',async()=>{
 render(<MatchCreateForm tournament={{id:'tour',timezone:'Europe/Moscow',revision:0} as Tournament} entries={[{id:'away',team:{name:'Юг'}} as Entry]} rules={[{id:'reg',variant_name:'Основной',version:1,rules:{}} as RegVersion]} onSaved={()=>{}}/>);
 fireEvent.change(screen.getByLabelText('Гости'),{target:{value:'away'}});fireEvent.change(screen.getByLabelText('Дата и время · Europe/Moscow'),{target:{value:'2026-10-20T19:00'}});fireEvent.click(screen.getByRole('button',{name:'Создать команду для хозяев'}));fireEvent.click(await screen.findByRole('button',{name:'Сохранить новую команду'}));await waitFor(()=>expect(screen.getByLabelText('Хозяева')).toHaveValue('new-entry'));expect(screen.getByLabelText('Хозяева')).toHaveValue('new-entry');expect(screen.getByLabelText('Гости')).toHaveValue('away');expect(screen.getByLabelText('Дата и время · Europe/Moscow')).toHaveValue('2026-10-20T19:00');
});
