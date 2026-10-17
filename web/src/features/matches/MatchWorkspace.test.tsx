import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {useEffect} from 'react';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import preset from '../../test/preset.json';

const owners=vi.hoisted(()=>({active:0,max:0,mounts:0,analytics:true,enqueue:vi.fn(async()=>{})}));
vi.mock('../auth/Auth',()=>({useAuth:()=>({session:{id:'admin-1',can_manage_analytics:owners.analytics}})}));
vi.mock('../protocol/useProtocolCommands',()=>({useProtocolCommands:()=>{
 useEffect(()=>{owners.active++;owners.mounts++;owners.max=Math.max(owners.max,owners.active);return()=>{owners.active--}},[]);
 return {queue:{view:fixture,items:[],blocked:false,error:undefined,enqueue:owners.enqueue,retry:async()=>{},refresh:async()=>{}},store:{error:undefined,raw:null},error:undefined};
}}));
vi.mock('./MatchPage',()=>({Lineups:()=><p>форма состава</p>,MatchInfo:()=><p>форма сведений</p>}));
vi.mock('./MatchReportTab',()=>({MatchReportTab:()=><p>отчёт без очереди</p>}));
vi.mock('../publication/MatchPublication',()=>({MatchPublication:()=><p>разрешение статистики</p>}));
vi.mock('../ratings/ParticipationEditor',()=>({ParticipationEditor:()=><p>участие</p>}));
vi.mock('../ratings/ActionReview',()=>({ActionReview:()=><p>действия</p>}));
vi.mock('../analysis/AnalysisTab',()=>({VideoAnalysisTab:({canManage}:{canManage:boolean})=><p>проверка записи {canManage?'Админ+':'обычная'}</p>}));
import {MatchWorkspacePage} from './MatchWorkspace';

const M='11111111-1111-4111-8111-111111111111';
const totals=()=>({score:null,fouls:null,yellow_cards:null,dismissals:null,period_scores:{}});
const fixture={id:M,tournament_id:'t1',revision:4,status:'ended',scheduled_at:'2026-10-20T15:00:00Z',venue_label:'Зал 1',hall_id:'h1',
 hall_snapshot:{id:'h1',name:'Зал 1',address:'Спортивная, 1'},camera_profile_id:null,broadcast_url:null,broadcast_embed_url:null,
 home:{team:{id:'a',name:'Север'}},away:{team:{id:'b',name:'Юг'}},lineup:[],published_version_id:null,server_now_ms:0,
 regulation:{rules:preset},regulation_override:null,clock:{period:1,phase:'not_started',elapsed_ms:0},
 protocol:{draft:true,events:[],reported_totals:{home:totals(),away:totals()},shootout_totals:{home:null,away:null},result_type:'played',technical_reason:null,
  completeness:{goals:'unknown',assists:'unknown',fouls:'unknown',cards:'unknown',lineup:'unknown',time:'unknown'},notes:'',public_notes:'',attachments:[]},
 projection:{effective_score:{home:null,away:null},event_score:{home:0,away:0},warnings:[],incomplete_sections:['goals']}};

let search='';const paths:string[]=[];
function Probe(){search=useLocation().search;return null}
const show=(query:string)=>render(<MemoryRouter initialEntries={[`/matches/${M}${query}`]}><Routes>
 <Route path="/matches/:id" element={<><MatchWorkspacePage/><Probe/></>}/></Routes></MemoryRouter>);
beforeEach(()=>{localStorage.clear();paths.length=0;Object.assign(owners,{active:0,max:0,mounts:0,analytics:true});owners.enqueue.mockClear();
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{const path=String(input);paths.push(path);
  const body=path.includes('/tournaments/')?{id:'t1',name:'Кубок',timezone:'Europe/Moscow',season:'2026'}
   :/attachments|history|versions/.test(path)?{items:[],total:0}:fixture;
  return new Response(JSON.stringify(body))}));});
afterEach(()=>vi.unstubAllGlobals());
// Матч перечитывается при смене задачи: ссылку дожидаемся, а не ищем сразу.
const go=async(user:ReturnType<typeof userEvent.setup>,name:string)=>user.click(await screen.findByRole('link',{name}));

describe('match workspace',()=>{
 it('keeps at most one protocol queue and none in read-only tasks',async()=>{
  const user=userEvent.setup();show('?tab=history');
  expect(await screen.findByText('Все изменения сохранены')).toBeInTheDocument();
  expect(owners.active).toBe(1);
  // Шаги раздела видны, когда он открыт: «Протокол» → «Состав».
  expect(screen.queryByRole('link',{name:'Состав'})).toBeNull();
  await go(user,'Протокол');await go(user,'Состав');expect(await screen.findByText('форма состава')).toBeInTheDocument();
  expect(owners.mounts).toBe(1);
  await go(user,'Публикация');expect(await screen.findByText('разрешение статистики')).toBeInTheDocument();
  expect(owners.active).toBe(0);
  await go(user,'Предпросмотр');expect(await screen.findByText('отчёт без очереди')).toBeInTheDocument();
  expect(owners.active).toBe(0);
  await go(user,'Протокол');await go(user,'Сведения');expect(await screen.findByText('форма сведений')).toBeInTheDocument();
  expect(owners.active).toBe(1);expect(owners.max).toBe(1);
  expect(localStorage.length).toBe(0);
 });
 it('hides Admin+ tasks from an ordinary admin without requesting them',async()=>{
  owners.analytics=false;show('?tab=participation');
  expect(await screen.findByRole('heading',{name:'Подготовка'})).toBeInTheDocument();
  await waitFor(()=>expect(new URLSearchParams(search).get('tab')).toBe('overview'));
  // У обычного администратора в «Видео» один шаг — строки шагов нет.
  await userEvent.setup().click(screen.getByRole('link',{name:'Видео'}));
  expect(await screen.findByText('проверка записи обычная')).toBeInTheDocument();
  expect(screen.queryByRole('link',{name:'Проверка'})).toBeNull();
  expect(screen.queryByRole('link',{name:'Участие'})).toBeNull();
  expect(screen.queryByRole('link',{name:'Действия'})).toBeNull();
  expect(paths.some(p=>/participation|performance-actions|ratings|understanding/.test(p))).toBe(false);
 });
 it('redirects old analysis links to the review task',async()=>{
  show('?tab=analysis');
  expect(await screen.findByText('проверка записи Админ+')).toBeInTheDocument();
  await waitFor(()=>expect(new URLSearchParams(search).get('tab')).toBe('review'));
 });
 it('shows readiness with fix links; missing camera does not block the protocol',async()=>{
  show('');
  expect(await screen.findByText(/Не выбрана — нужна только для видеоанализа/)).toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Выбрать камеру'})).toHaveAttribute('href','/matches/'+M+'?tab=info');
  expect(screen.getByRole('link',{name:'Отметить состав'})).toHaveAttribute('href','/matches/'+M+'?tab=lineup');
  // Один следующий шаг: зал выбран, состава нет.
  const next=screen.getByRole('region',{name:'Следующий шаг'});
  expect(next).toHaveTextContent('Отметьте состав');
  expect(screen.getByRole('link',{name:/К составу/})).toHaveAttribute('href','/matches/'+M+'?tab=lineup');
 });
 it('records only the result in «Только итог» and keeps the mode',async()=>{
  const user=userEvent.setup();const {unmount}=show('?tab=protocol');
  await user.click(await screen.findByRole('button',{name:'Только итог'}));
  expect(screen.queryByRole('button',{name:'Гол'})).toBeNull();
  await user.type(screen.getByLabelText('Счёт хозяев'),'3');await user.type(screen.getByLabelText('Счёт гостей'),'2');
  await user.click(screen.getByRole('button',{name:'Сохранить итоги'}));
  expect(owners.enqueue).toHaveBeenCalledTimes(1);
  const [command]=owners.enqueue.mock.calls[0] as unknown as [{kind:string;payload:{reported_totals:{home:{score:number}}}}];
  expect(command.kind).toBe('set_totals');
  expect(command.payload.reported_totals.home.score).toBe(3);
  expect(owners.enqueue.mock.calls.some(c=>(c as unknown as [{kind:string}])[0].kind==='set_completeness')).toBe(false);
  unmount();show('?tab=protocol');
  expect(await screen.findByRole('button',{name:'Только итог'})).toHaveAttribute('aria-pressed','true');
 });
});
