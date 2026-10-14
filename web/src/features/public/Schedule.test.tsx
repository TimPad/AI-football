import {it,expect} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {Schedule} from './Schedule';
import type {PublicMatch} from '../../api/domain';

const matches = [
 {id:'one',scheduled_at:'2026-10-19T22:30:00Z',venue_label:'Зал 1',home_name:'Север',away_name:'Юг',status:'scheduled',schedule_slot_s:5400,score:{home:null,away:null},broadcast_url:'https://vk.com/video-1_2'},
 {id:'two',scheduled_at:'2026-10-20T16:00:00Z',venue_label:'Зал 2',home_name:'Восток',away_name:'Запад',status:'ended',schedule_slot_s:3600,score:{home:3,away:2},broadcast_url:null},
] as PublicMatch[];

it('filters a local day, switches timetable/list and links to match details',()=>{
 render(<MemoryRouter><Schedule matches={matches} timezone="Europe/Moscow"/></MemoryRouter>);
 fireEvent.change(screen.getByLabelText('Дата'),{target:{value:'2026-10-20'}});
 expect(screen.getByRole('link',{name:/Север.*Юг/})).toHaveAttribute('href','/watch/matches/one');
 fireEvent.click(screen.getByRole('button',{name:'Сетка расписания'}));
 expect(screen.getByRole('table',{name:'Сетка расписания'})).toHaveTextContent('01:30');
 expect(screen.getByRole('table',{name:'Сетка расписания'})).toHaveTextContent('03:00');
 expect(screen.getByRole('table',{name:'Сетка расписания'})).toHaveTextContent('Зал 2');
 fireEvent.change(screen.getByLabelText('Площадка'),{target:{value:'Зал 2'}});
 expect(screen.queryByRole('link',{name:/Север.*Юг/})).toBeNull();
 expect(screen.getByRole('link',{name:/Восток.*Запад/})).toHaveTextContent('3 : 2');
 fireEvent.change(screen.getByLabelText('Дата'),{target:{value:'2026-10-21'}});
 expect(screen.getByText('На эту дату матчей нет.')).toBeVisible();
});

it('keeps two halls with the same name in separate columns and filters by identity',()=>{
 const duplicate=matches.map((m,i)=>({...m,venue_label:'Арена',hall:{id:`hall-${i}`,name:'Арена',address:`Адрес ${i}`,pitch_length_m:40,pitch_width_m:20},scheduled_at:'2026-10-20T16:00:00Z'}));
 render(<MemoryRouter><Schedule matches={duplicate} timezone="Europe/Moscow"/></MemoryRouter>);
 fireEvent.change(screen.getByLabelText('Дата'),{target:{value:'2026-10-20'}});
 fireEvent.click(screen.getByRole('button',{name:'Сетка расписания'}));
 expect(screen.getAllByRole('columnheader',{name:/Арена/})).toHaveLength(2);
 fireEvent.change(screen.getByLabelText('Площадка'),{target:{value:'hall-1'}});
 expect(screen.queryByRole('link',{name:/Север.*Юг/})).toBeNull();
 expect(screen.getByRole('link',{name:/Восток.*Запад/})).toBeVisible();
});
