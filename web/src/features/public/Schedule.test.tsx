import {it,expect} from 'vitest';
import {render,screen,fireEvent,within} from '@testing-library/react';
import {MemoryRouter,Route,Routes,useLocation,useNavigate} from 'react-router-dom';
import {Schedule,type ScheduleItem} from './Schedule';

const matches = [
 {id:'one',scheduled_at:'2026-10-19T22:30:00Z',venue_label:'Зал 1',home_name:'Север',away_name:'Юг',status:'scheduled',schedule_slot_s:5400,score:{home:null,away:null},broadcast_url:'https://vk.com/video-1_2',broadcast_embed_url:null},
 {id:'two',scheduled_at:'2026-10-20T16:00:00Z',venue_label:'Зал 2',home_name:'Восток',away_name:'Запад',status:'ended',schedule_slot_s:3600,score:{home:3,away:2},broadcast_url:null,broadcast_embed_url:null},
] as ScheduleItem[];
let search='';
function Probe(){search=useLocation().search;return null}
function Away(){const go=useNavigate();return <button onClick={()=>go('/elsewhere')}>уйти</button>}
function Back(){const go=useNavigate();return <button onClick={()=>go(-1)}>назад</button>}
const show=(entry:string,items=matches,href?:(id:string)=>string)=>render(<MemoryRouter initialEntries={[entry]}><Routes>
 <Route path="/t" element={<><Schedule matches={items} timezone="Europe/Moscow" matchHref={href}/><Probe/><Away/></>}/>
 <Route path="/elsewhere" element={<Back/>}/></Routes></MemoryRouter>);
const open=(name:RegExp)=>screen.getByRole('link',{name});

it('carries schedule context through a grid match link',()=>{
 let received:unknown;const saved={scheduleReturn:'/t?tab=matches&view=grid&day=2026-10-20'};
 function Target(){received=useLocation().state;return null}
 render(<MemoryRouter initialEntries={['/t?view=grid&day=2026-10-20']}><Routes><Route path="/t" element={<Schedule matches={matches} timezone="Europe/Moscow" matchHref={id=>`/m/${id}`} matchState={saved}/>}/><Route path="/m/:id" element={<Target/>}/></Routes></MemoryRouter>);
 fireEvent.click(open(/Север — Юг/));expect(received).toEqual(saved);
});

it('switches timetable/list, filters a hall and links to match details',()=>{
 show('/t');
 // Оба матча в один местный день: выбирать дату не из чего.
 expect(screen.queryByLabelText('Дата')).toBeNull();
 expect(open(/Север — Юг/)).toHaveAttribute('href','/watch/matches/one');
 fireEvent.click(screen.getByRole('button',{name:'Сетка'}));
 const grid=screen.getByRole('table',{name:'Сетка расписания'});
 expect(grid).toHaveTextContent('01:30 – 03:00');
 expect(grid).toHaveTextContent('Зал 2');
 fireEvent.change(screen.getByLabelText('Фильтр по залу'),{target:{value:'Зал 2'}});
 expect(screen.queryByRole('link',{name:/Север — Юг/})).toBeNull();
 expect(screen.getByRole('table',{name:'Сетка расписания'})).toHaveTextContent('3 : 2');
});

it('shows a filter only when it can change something',()=>{
 const one=[{...matches[1],hall:{id:'h',name:'Арена',address:'Улица, 1',pitch_length_m:40,pitch_width_m:20}}] as ScheduleItem[];
 const {container,unmount}=show('/t',one);
 // Один матч, один зал, один день: без панели фильтров, зал — без адреса.
 expect(container.querySelector('.schedule-toolbar')).toBeNull();
 expect(container.querySelector('.row-hall')).toHaveTextContent(/^Арена$/);
 expect(container.querySelector('.schedule-foot')).toHaveTextContent('1 матчВремя московское');
 unmount();
 // Фильтр из ссылки остаётся видимым, чтобы его можно было сбросить.
 show('/t?day=2026-10-21',one);
 expect(screen.getByText('Матчей с такими условиями нет.')).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Сбросить'}));
 expect(open(/Восток — Запад/)).toBeVisible();
 const many=Array.from({length:11},(_,i)=>({...matches[1],id:`m${i}`,scheduled_at:`2026-10-${10+i}T16:00:00Z`}));
 show('/t',many);
 expect(screen.getByLabelText('Фильтр по статусу')).toBeInTheDocument();
 expect(screen.getByLabelText('Дата')).toBeInTheDocument();
 expect(screen.queryByLabelText('Фильтр по залу')).toBeNull();
 expect(screen.queryByRole('button',{name:'Сетка'})).toBeNull();
});

it('keeps two halls with the same name in separate columns and filters by identity',()=>{
 const duplicate=matches.map((m,i)=>({...m,venue_label:'Арена',hall:{id:`hall-${i}`,name:'Арена',address:`Адрес ${i}`,pitch_length_m:40,pitch_width_m:20},scheduled_at:'2026-10-20T16:00:00Z'}));
 show('/t?view=grid&day=2026-10-20',duplicate);
 expect(screen.getAllByRole('columnheader',{name:/Арена/})).toHaveLength(2);
 fireEvent.change(screen.getByLabelText('Фильтр по залу'),{target:{value:'hall-1'}});
 expect(screen.queryByRole('link',{name:/Север — Юг/})).toBeNull();
 expect(open(/Восток — Запад/)).toBeVisible();
});

it('opens the URL state, keeps null score as a dash and restores filters after Back',()=>{
 show('/t?tab=matches&view=grid&day=2026-10-20&hall_id=Зал 2&status=ended',matches,id=>`/matches/${id}`);
 const grid=screen.getByRole('table',{name:'Сетка расписания'});
 expect(within(grid).getAllByRole('columnheader')).toHaveLength(2);
 expect(open(/Восток — Запад/)).toHaveAttribute('href','/matches/two');
 expect(screen.getByLabelText('Фильтр по статусу')).toHaveValue('ended');
 fireEvent.change(screen.getByLabelText('Фильтр по статусу'),{target:{value:''}});
 fireEvent.change(screen.getByLabelText('Фильтр по залу'),{target:{value:''}});
 fireEvent.change(screen.getByLabelText('Дата'),{target:{value:'2026-10-20'}});
 expect(screen.getByLabelText('Результат не опубликован')).toHaveTextContent('— : —');
 expect(new URLSearchParams(search).get('tab')).toBe('matches');
 expect(new URLSearchParams(search).get('view')).toBe('grid');
 fireEvent.click(screen.getByRole('button',{name:'уйти'}));
 fireEvent.click(screen.getByRole('button',{name:'назад'}));
 expect(new URLSearchParams(search).get('day')).toBe('2026-10-20');
 expect(screen.getByRole('table',{name:'Сетка расписания'})).toBeInTheDocument();
});

it('draws slot heights proportional to time and keeps overlaps side by side',()=>{
 const items=[{...matches[1],id:'a',scheduled_at:'2026-10-20T15:00:00Z',schedule_slot_s:5400,status:'scheduled',score:{home:null,away:null}},
  {...matches[1],id:'b',scheduled_at:'2026-10-20T15:30:00Z',schedule_slot_s:1800,home_name:'Альфа',away_name:'Бета'},
  {...matches[1],id:'c',scheduled_at:'2026-10-20T17:00:00Z',schedule_slot_s:3600,status:'cancelled',home_name:'Гамма',away_name:'Дельта'}] as ScheduleItem[];
 const {container}=show('/t?view=grid&day=2026-10-20',items);
 const slots=[...container.querySelectorAll<HTMLElement>('.time-slot')];
 const px=(e:HTMLElement,k:'top'|'height')=>parseFloat(e.style[k]);
 expect(px(slots[0],'height')/px(slots[1],'height')).toBe(3);
 expect(px(slots[2],'top')-px(slots[0],'top')).toBe(px(slots[0],'height')+px(slots[1],'height'));
 expect(slots[0].style.left).not.toBe(slots[1].style.left);
 expect(within(screen.getByRole('table',{name:'Сетка расписания'})).getByText('Отменён')).toBeVisible();
 expect(container.querySelector('.time-axis')).toHaveTextContent('18:0018:3019:0019:3020:0020:3021:00');
 // Высота задаётся ячейкам: строка с display:contents её не передаёт.
 expect(parseFloat(container.querySelector<HTMLElement>('.time-column')!.style.height)).toBe(180*1.6);
});

it('filters teams by stable identity and provides public profile links',()=>{
 const items=matches.map((m,i)=>({...m,home_team_id:`home-${i}`,away_team_id:`away-${i}`}));
 render(<MemoryRouter initialEntries={['/t?team_id=home-1']}><Schedule matches={items} timezone="Europe/Moscow" teamHref={id=>`/teams/${id}`}/></MemoryRouter>);
 expect(screen.getByLabelText('Фильтр по команде')).toHaveValue('home-1');
 expect(screen.queryByRole('link',{name:/Север — Юг/})).toBeNull();
 expect(screen.getByRole('link',{name:'Восток'})).toHaveAttribute('href','/teams/home-1');
});
