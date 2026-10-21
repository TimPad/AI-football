import {afterEach,it,expect,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {useState} from 'react';
import {DateNavigation} from './DateNavigation';
afterEach(()=>vi.useRealTimers());
it('crosses the year and computes today at the time of clicking',()=>{
 vi.useFakeTimers();vi.setSystemTime(new Date('2026-12-31T20:00:00Z'));
 function Harness(){const [day,setDay]=useState('2026-12-31');return <DateNavigation day={day} onDayChange={setDay}/>}
 render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'Следующий день'}));expect(screen.getByLabelText('Дата матчей')).toHaveValue('2027-01-01');
 vi.setSystemTime(new Date('2027-01-02T22:00:00Z'));fireEvent.click(screen.getByRole('button',{name:'Сегодня'}));expect(screen.getByLabelText('Дата матчей')).toHaveValue('2027-01-03');
});
