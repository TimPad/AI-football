import {afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter,Route,Routes,useLocation,useNavigate} from 'react-router-dom';
import {PublicMatchPage} from './PublicMatchPage';

const A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
const P1='33333333-3333-4333-8333-333333333333',P2='44444444-4444-4444-8444-444444444444';
const HOME='55555555-5555-4555-8555-555555555555',AWAY='66666666-6666-4666-8666-666666666666';
const SNAP='77777777-7777-4777-8777-777777777777';
const match=(id:string,name='Север',extra={})=>({id,tournament:{id:'t1',name:'Кубок',timezone:'Europe/Moscow',season:'2026'},home_name:name,away_name:'Юг',
 home_team_id:HOME,away_team_id:AWAY,home_logo_id:'logo-h',away_logo_id:null,scheduled_at:'2026-10-20T15:00:00Z',venue_label:'Зал 1',hall:null,
 status:'ended',schedule_slot_s:5400,broadcast_url:null,broadcast_embed_url:null,public_protocol_id:'pp1',score:{home:3,away:2},...extra});
const protocol={number:2,confirmed_at:'2026-10-20T18:00:00Z',published_at:'2026-10-20T18:10:00Z',home_name:'Север',away_name:'Юг',
 scheduled_at:'2026-10-20T15:00:00Z',venue_label:'Зал 1',regulation:{total_s:2400,rules:{shootout:{enabled:false},periods_s:[1200,1200]}},
 lineup:[{player_id:P1,display_name:'Игрок 01',shirt_number:'7',side:'home'}],
 protocol:{events:[{id:'e1',kind:'goal',side:'home',period:1,elapsed_ms:60000,player_id:P1}],result_type:'played',technical_reason:null,public_notes:'',shootout_totals:{home:null,away:null},
  completeness:{goals:'complete',assists:'complete',fouls:'complete',cards:'complete',lineup:'complete',time:'complete'}},
 projection:{event_score:{home:1,away:0},shootout_score:{home:0,away:0},incomplete_sections:[],effective_score:{home:3,away:2},
  effective_totals:{home:{fouls:2,yellow_cards:0,dismissals:0},away:{fouls:4,yellow_cards:1,dismissals:0}},period_event_scores:{'1':{home:1,away:0}},accumulated_fouls:{home:{},away:{}}}};
const fact=(value:number|null,n:number|null,d:number|null,unit:string,reason:string|null=null)=>({value,numerator:n,denominator:d,unit,completeness:'complete',reason});
const rating={player_id:P1,display_name:'Игрок 01',role:'ala',team_id:HOME,team_name:'Север',match_id:A,scheduled_at:'2026-10-20T15:00:00Z',
 display_rating:7.2,score:68,coverage:1,eligible_play_minutes:12,played_minutes:12,appeared:true,components:{},contributions:{},feature_scores:{},
 reasons:[],model_version:'v1',reference_version:'r',profile_id:'per10',time_basis:'reviewed_effective',
 facts:{pass_completion_pct:fact(78.3,18,23,'percent'),pass_completion_unresolved_count:fact(2,2,null,'count'),
  shots_on_target_pct:fact(null,0,0,'percent','no_opportunities'),shots_on_target_unresolved_count:fact(0,0,null,'count')}};
const heat=[[0,0],[4,8]];
const analysis={match_id:A,run_id:'run-B',pitch:{length_m:41,width_m:15.5,cell_m:20,orientation:'camera'},teams:{},side_map:{A:'home',B:'away'},
 primary_period_key:'all',video_s:300,processed_s:186,partial:true,
 periods:[{key:'all',name:'Весь матч',duration_s:186,teams:{A:{distance_m:3420,heatmap_s:heat},B:{distance_m:3180,heatmap_s:[[0,12],[0,0]]}}}],
 players:[{player_id:P1,display_name:'Игрок 01',shirt_number:'7',side:'home',metrics:{distance_m:0,observed_s:60,m_per_min:null,hsr_m:0,sprints:0,vmax_ms:null,heatmap_s:heat}}]};

type Reply={status:number,body?:unknown,delay?:Promise<void>};
function stub(routes:(path:string)=>Reply|undefined){
 const paths:string[]=[];
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const path=String(input);paths.push(path);const reply=routes(path)??{status:404,body:{error:{code:'not_found',message:'Нет'}}};
  if(reply.delay)await reply.delay;
  init?.signal?.throwIfAborted();
  return new Response(JSON.stringify(reply.body??{}),{status:reply.status});
 }));
 return paths;
}
const standard=(path:string):Reply|undefined=>{
 if(path.endsWith(`/public/matches/${A}`))return {status:200,body:match(A)};
 if(path.includes('/public/protocols/pp1'))return {status:200,body:protocol};
 if(path.includes(`/public/matches/${A}/analysis`))return {status:200,body:analysis};
 if(path.includes(`/public/matches/${A}/ratings`))return {status:200,body:{snapshot_id:SNAP,items:[rating]}};
};
let location='';
function Probe(){location=useLocation().search;return null}
function Jump(){const go=useNavigate();return <button onClick={()=>go(`/watch/matches/${B}`)}>к матчу B</button>}
const show=(entry:string)=>render(<MemoryRouter initialEntries={[entry]}><Routes><Route path="/watch/matches/:id" element={<><PublicMatchPage/><Probe/><Jump/></>}/></Routes></MemoryRouter>);
afterEach(()=>vi.unstubAllGlobals());

describe('public match page',()=>{
 it('requests only public routes, header first, then the selected section',async()=>{
  const paths=stub(standard);
  show(`/watch/matches/${A}?tab=events`);
  expect(await screen.findByRole('heading',{name:'События'})).toBeInTheDocument();
  await waitFor(()=>expect(paths).toContain('/api/v1/public/protocols/pp1'));
  expect(paths[0]).toBe(`/api/v1/public/matches/${A}`);
  expect(paths.every(p=>p.startsWith('/api/v1/public/'))).toBe(true);
  expect(paths.some(p=>/analysis|ratings|\/players\/|\/versions/.test(p))).toBe(false);
  expect(document.querySelector('img')?.getAttribute('src')).toBe('/api/v1/public/catalog/team-logos/logo-h');
 });
 it('hides empty sections and does not request private history when no protocol is published',async()=>{
  const paths=stub(p=>p.endsWith(`/public/matches/${A}`)?{status:200,body:match(A,'Север',{public_protocol_id:null,score:{home:null,away:null}})}:undefined);
  show(`/watch/matches/${A}?tab=events`);
  expect(await screen.findByLabelText('Результат не опубликован')).toHaveTextContent('— : —');
  // Без протокола и трансляции вкладок «События» и «Видео» нет: ссылка на них открывает обзор.
  const nav=screen.getByRole('navigation',{name:'Разделы матча'});
  expect(within(nav).queryByRole('link',{name:'События'})).toBeNull();
  expect(within(nav).queryByRole('link',{name:'Видео'})).toBeNull();
  expect(within(nav).getByRole('link',{name:'Обзор'})).toHaveAttribute('aria-current','page');
  await waitFor(()=>expect(paths.some(p=>p.includes('/analysis'))).toBe(true));
  expect(screen.queryByRole('heading',{name:'Ключевые события'})).toBeNull();
  expect(paths.every(p=>p.startsWith('/api/v1/public/'))).toBe(true);
  expect(paths.some(p=>p.includes('/protocols/'))).toBe(false);
 });
 it('keeps the edition with a rating selection and does not attach current CV as its map',async()=>{
  stub(standard);const user=userEvent.setup();
  show(`/watch/matches/${A}?tab=stats&group=passes`);
  const table=await screen.findByRole('table',{name:'Показатели игроков'});
  expect(within(table).getByText('18 / 23 · 78%')).toBeInTheDocument();
  expect(within(table).getByText('Неопределённых исходов: 2')).toBeInTheDocument();
  await user.click(within(table).getByRole('button',{name:'Игрок 01'}));
  const params=new URLSearchParams(location);
  expect(params.get('origin')).toBe('rating');
  expect(params.get('snapshot_id')).toBe(SNAP);
  const card=screen.getByRole('dialog',{name:'Игрок 01'});
  expect(within(card).getByText('Для этой оценки карты нет')).toBeInTheDocument();
  expect(card.querySelectorAll('rect.heat-cell')).toHaveLength(0);
  await user.click(within(card).getByRole('button',{name:'Открыть карту по видео'}));
  expect(new URLSearchParams(location).get('origin')).toBe('cv');
  const cv=screen.getByRole('dialog',{name:'Игрок 01'});
  expect(cv.querySelectorAll('rect.heat-cell')).toHaveLength(2);
  expect(within(cv).getByText(/индивидуальная шкала/)).toBeInTheDocument();
  expect(within(cv).queryByText(/Роль в матче: (Фиксо|Пивот)/)).toBeNull();
 });
 it('shows no fake zero percent and labels a partial period as processed fragment',async()=>{
  stub(standard);
  show(`/watch/matches/${A}?tab=stats&group=shots`);
  const table=await screen.findByRole('table',{name:'Показатели игроков'});
  expect(within(table).getByText('Не было наблюдаемых возможностей')).toBeInTheDocument();
  expect(within(table).queryByText(/0%/)).toBeNull();
  expect(screen.getByText('По обработанному фрагменту записи')).toBeInTheDocument();
  // Максимум хозяев 8 с, гостей 12 с: обе карты на одной шкале 0–12.
  expect(screen.getAllByText(/0 — 12 с · общая шкала обеих команд/)).toHaveLength(2);
 });
 it('isolates CV failure and absent ratings from the protocol',async()=>{
  const paths=stub(path=>{
   if(path.includes('/analysis'))return {status:500,body:{error:{code:'x',message:'Сбой видеоанализа'}}};
   if(path.includes('/ratings'))return {status:404,body:{error:{code:'not_found',message:'Нет'}}};
   return standard(path);
  });
  const user=userEvent.setup();
  show(`/watch/matches/${A}`);
  expect(await screen.findByText('Сбой видеоанализа')).toBeInTheDocument();
  expect(screen.getByRole('list',{name:'Лента матча'})).toHaveTextContent('Игрок 01');
  expect(screen.getByLabelText('Счёт 3 : 2')).toBeInTheDocument();
  const before=paths.length;
  await user.click(screen.getByRole('button',{name:'Повторить'}));
  await waitFor(()=>expect(paths.length).toBeGreaterThan(before));
  expect(paths.some(p=>p.includes('understanding'))).toBe(false);
 });
 it('opens player movement by default when there are CV metrics but no published ratings',async()=>{
  stub(path=>path.includes('/ratings')?{status:404,body:{error:{code:'not_found',message:'Нет'}}}:standard(path));
  show(`/watch/matches/${A}?tab=stats`);
  const table=await screen.findByRole('table',{name:'Показатели игроков'});
  expect(within(table).getByText('Дистанция, м')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Перемещения'})).toHaveAttribute('aria-pressed','true');
 });
 it('does not render a late response of the previous match',async()=>{
  let release!:()=>void;const late=new Promise<void>(r=>{release=r});
  stub(path=>{
   if(path.endsWith(`/public/matches/${A}`))return {status:200,body:match(A,'Медленный'),delay:late};
   if(path.endsWith(`/public/matches/${B}`))return {status:200,body:match(B,'Быстрый',{public_protocol_id:null})};
  });
  const user=userEvent.setup();
  show(`/watch/matches/${A}?tab=video`);
  await user.click(screen.getByRole('button',{name:'к матчу B'}));
  expect(await screen.findByText('Быстрый')).toBeInTheDocument();
  release();await new Promise(r=>setTimeout(r,10));
  expect(screen.queryByText('Медленный')).toBeNull();
 });
 it('explains an unknown player without a catalogue lookup',async()=>{
  const paths=stub(standard);
  show(`/watch/matches/${A}?tab=players&player_id=${P2}`);
  expect(await screen.findByText('Этого игрока нет в опубликованных данных матча.')).toBeInTheDocument();
  expect(paths.some(p=>p.includes(P2))).toBe(false);
 });
 it('rejects a malformed id without requests',()=>{
  const paths=stub(standard);
  show('/watch/matches/not-a-uuid');
  expect(screen.getByRole('alert')).toHaveTextContent('Неверная ссылка на матч.');
  expect(paths).toEqual([]);
 });
});
