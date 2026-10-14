import {it,expect,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {all} from '../../api/client';
import {HallSelection} from './HallSelection';
vi.mock('../../api/client',()=>({all:vi.fn(),errorText:(e:Error)=>e.message}));
it('refreshes halls and camera profiles without remounting or losing current input',async()=>{
 const hall={id:'hall',name:'Арена',address:'Спортивная 1',pitch_length_m:40,pitch_width_m:20,archived:false};
 let updated=false;
 vi.mocked(all).mockImplementation(async(path:string)=>path==='/halls'?[hall,...(updated?[{...hall,id:'new',name:'Новый зал'}]:[])]:updated?[{id:'camera',hall_id:'hall',name:'Основная',version:1,frame_width:1000,frame_height:500,pitch_length_m:40,pitch_width_m:20}]:[]);
 const change=vi.fn();
 render(<MemoryRouter><input aria-label="Несохранённое время" defaultValue="19:00"/><HallSelection hallId="hall" cameraId="" onChange={change}/></MemoryRouter>);
 expect(await screen.findByRole('option',{name:/Арена/})).toBeVisible();
 updated=true;fireEvent.click(screen.getByRole('button',{name:'Обновить залы и камеры'}));
 expect(await screen.findByRole('option',{name:/Новый зал/})).toBeVisible();
 expect(await screen.findByRole('option',{name:/Основная.*версия 1/})).toBeVisible();
 expect(screen.getByLabelText('Несохранённое время')).toHaveValue('19:00');
 expect(screen.getByLabelText('Зал')).toHaveValue('hall');expect(change).not.toHaveBeenCalled();
});
