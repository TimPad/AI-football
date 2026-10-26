import {afterEach,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {MemoryRouter,Routes,Route,useNavigate,useLocation} from 'react-router-dom';
import {PublicMatchCenter} from './PublicMatchCenter';
const t={id:'a',name:'Кубок',season:'2026'},u={...t,id:'b'};
const match=(id:string,tournament=t)=>({id,tournament,home_name:'Север '+id,away_name:'Юг',scheduled_at:'2026-10-20T18:00:00Z',status:'scheduled',score:{home:null,away:null}});
const day=(items:unknown[],cursor:string|null=null)=>({day:'2026-10-20',timezone:'Europe/Moscow',generated_at:'2026-10-18T10:00:00Z',items,total:3,next_cursor:cursor,tournament_totals:{a:2,b:1}});
afterEach(()=>{vi.unstubAllGlobals();sessionStorage.clear()});
it('keeps same-name groups distinct and merges the next page without duplicating matches',async()=>{
 vi.stubGlobal('fetch',vi.fn(async input=>{const path=String(input);return new Response(JSON.stringify(path.includes('/ratings')?{items:[],snapshot_id:null}:path.includes('/upcoming')?{items:[]}:path.includes('/tournaments?')?{items:[t,u],total:2}:path.includes('cursor=next')?day([match('1'),match('2'),match('3',u)]):day([match('1')],'next')))}));
 render(<MemoryRouter initialEntries={['/?day=2026-10-20']}><PublicMatchCenter/></MemoryRouter>);
 await screen.findByRole('link',{name:'Открыть матч Север 1 — Юг'});fireEvent.click(screen.getByRole('button',{name:'Ещё матчи'}));
 await screen.findByRole('link',{name:'Открыть матч Север 3 — Юг'});expect(screen.getAllByRole('link',{name:'Открыть турнир Кубок'})).toHaveLength(2);expect(screen.getAllByRole('link',{name:'Открыть матч Север 1 — Юг'})).toHaveLength(1);
});
it('does not show a stale day under a newly selected date',async()=>{
 let release:((v:Response)=>void)|undefined;
 vi.stubGlobal('fetch',vi.fn(async input=>{const path=String(input);if(path.includes('/upcoming'))return new Response('{"items":[]}');if(path.includes('/ratings'))return new Response('{"items":[],"snapshot_id":null}');if(path.includes('/tournaments?'))return new Response('{"items":[],"total":0}');if(path.includes('day=2026-10-21'))return new Promise<Response>(r=>{release=r});return new Response(JSON.stringify(day([match('old')])))}));
 render(<MemoryRouter initialEntries={['/?day=2026-10-20']}><PublicMatchCenter/></MemoryRouter>);await screen.findByText('Север old');
 fireEvent.click(screen.getByRole('button',{name:'Следующий день'}));expect(screen.queryByText('Север old')).not.toBeInTheDocument();
 await waitFor(()=>expect(release).toBeDefined());release!(new Response(JSON.stringify({...day([]),day:'2026-10-21'})));await screen.findByText(/матчей нет/);
});

it('restores loaded pages when returning from a match and refreshes them together',async()=>{
 vi.stubGlobal('fetch',vi.fn(async input=>{const path=String(input);return new Response(JSON.stringify(path.includes('/ratings')?{items:[],snapshot_id:null}:path.includes('/upcoming')?{items:[]}:path.includes('/tournaments?')?{items:[t],total:1}:path.includes('cursor=next')?day([match('2')]):day([match('1')],'next')))}));
 function Back(){const go=useNavigate();return <button onClick={()=>go(-1)}>Вернуться</button>}
 render(<MemoryRouter initialEntries={['/?day=2026-10-20']}><Routes><Route path="/" element={<PublicMatchCenter/>}/><Route path="/watch/matches/:id" element={<Back/>}/></Routes></MemoryRouter>);
 await screen.findByRole('button',{name:'Ещё матчи'});fireEvent.click(screen.getByRole('button',{name:'Ещё матчи'}));
 fireEvent.click(await screen.findByRole('link',{name:'Открыть матч Север 2 — Юг'}));fireEvent.click(screen.getByRole('button',{name:'Вернуться'}));
 await screen.findByRole('link',{name:'Открыть матч Север 2 — Юг'});
 // Returning to the tab refreshes in place: the loaded rows stay on screen instead of «Загружаем…».
 await screen.findByText('Рейтинг ещё не опубликован.');
 Object.defineProperty(document,'visibilityState',{value:'visible',configurable:true});fireEvent(document,new Event('visibilitychange'));expect(screen.queryByText('Загружаем…')).toBeNull();
 await waitFor(()=>expect(vi.mocked(fetch).mock.calls.filter(([p])=>String(p).includes('cursor=next')).length).toBe(2));
 expect(screen.getAllByRole('link',{name:/Открыть матч Север/})).toHaveLength(2);
});

it('opens a match from the whole row and keeps the guess of leaders out of the link',async()=>{
 vi.stubGlobal('fetch',vi.fn(async input=>{const path=String(input);return new Response(JSON.stringify(path.includes('/ratings')?{items:[],snapshot_id:null}:path.includes('/upcoming')?{items:[]}:path.includes('/tournaments?')?{items:[t],total:1}:day([match('1')])))}));
 render(<MemoryRouter initialEntries={['/?day=2026-10-20']}><Routes><Route path="/" element={<><PublicMatchCenter/><Where/></>}/></Routes></MemoryRouter>);
 const row=await screen.findByRole('link',{name:'Открыть матч Север 1 — Юг'});
 expect(row).toHaveAttribute('href','/watch/matches/1');expect(row).toHaveTextContent('Север 1');
 expect(screen.queryByRole('link',{name:'Север 1'})).toBeNull();expect(row.textContent).not.toMatch(/Запланирован/);
 expect(screen.getByTestId('where').textContent).not.toContain('leaders_tournament_id');expect(document.title).toBe('Матчи — AI Football');
});
it('fills an empty day with neighbouring game days, recent results and the nearest games',async()=>{
 const finished={...match('old'),status:'ended',scheduled_at:'2026-10-17T16:00:00Z',score:{home:2,away:1}};
 vi.stubGlobal('fetch',vi.fn(async input=>{const path=String(input);return new Response(JSON.stringify(path.includes('/ratings')?{items:[],snapshot_id:null}:path.includes('/recent')?{items:[finished]}:path.includes('/upcoming')?{items:[match('next')]}:path.includes('/tournaments?')?{items:[t],total:1}:path.includes('day=2026-10-17')?{...day([finished]),day:'2026-10-17'}:{...day([]),total:0,previous_day:'2026-10-17',next_day:'2026-10-25'}))}));
 render(<MemoryRouter initialEntries={['/?day=2026-10-20']}><Routes><Route path="/" element={<><PublicMatchCenter/><Where/></>}/></Routes></MemoryRouter>);
 await screen.findByText('20 октября матчей нет');
 expect(await screen.findByRole('heading',{name:'Последние результаты'})).toBeInTheDocument();expect(screen.getByRole('link',{name:'Открыть матч Север old — Юг, 2 : 1'})).toBeInTheDocument();
 expect(screen.getByRole('heading',{name:'Ближайшие матчи'})).toBeInTheDocument();expect(screen.getByRole('link',{name:'Открыть матч Север next — Юг'})).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/Предыдущий игровой день/}));
 await waitFor(()=>expect(screen.getByTestId('where').textContent).toContain('day=2026-10-17'));
 expect(await screen.findByRole('link',{name:'Открыть матч Север old — Юг, 2 : 1'})).toBeInTheDocument();expect(screen.queryByText(/матчей нет/)).toBeNull();
});
function Where(){const location=useLocation();return <output data-testid="where">{location.search}</output>}
