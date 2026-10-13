import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {RegulationForm} from './RegulationForm';
import preset from '../../test/preset.json';
import type {Regulation} from '../../api/domain';
import {vi,it,expect} from 'vitest';
it('shows duration and submits period lengths in seconds',async()=>{
 const save=vi.fn().mockResolvedValue(undefined);
 render(<RegulationForm initial={preset as Regulation} onSave={save}/>);
 const user=userEvent.setup();const field=screen.getByLabelText('Длительность тайма 1, минут');
 await user.clear(field);await user.type(field,'15');
 expect(screen.getByText('Основное время: 35 минут')).toBeVisible();
 await user.click(screen.getByRole('button',{name:'Сохранить регламент'}));
 expect(save.mock.calls[0][0].periods_s).toEqual([900,1200]);
});
it('keeps form values and displays server field errors',async()=>{
 const save=vi.fn().mockRejectedValue(new Error('Лимиты заявки должны вмещать игроков на поле'));
 render(<RegulationForm initial={preset as Regulation} onSave={save}/>);
 await userEvent.click(screen.getByRole('button',{name:'Сохранить регламент'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Лимиты заявки');
 expect(screen.getByLabelText('Игроков на поле')).toHaveValue(5);
});
