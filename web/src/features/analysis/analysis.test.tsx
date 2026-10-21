import {it,expect,vi,beforeEach} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {AnalysisReport} from './AnalysisReport';
import {IdentityReview} from './IdentityReview';
import {VideoAnalysisTab} from './AnalysisTab';
import {sendJson,readPending} from './commands';
import {ApiError} from '../../api/client';
import type {AnalysisRun} from '../../api/domain';
vi.mock('../../api/client',async()=>{const actual=await vi.importActual<typeof import('../../api/client')>('../../api/client');return {...actual,api:vi.fn(),post:vi.fn()}});
import {api} from '../../api/client';
const run={id:'run',job_id:'job',match_id:'match',revision:0,analysis_revision:0,status:'review',source_run_id:null,created_at:'2026-10-13',partial:true,passed:true,active_run_id:null,published_run_id:null,manifest:{source_video:{duration_s:240}},report:{match:{processed_s:120},pitch:{length_m:40,width_m:20},periods:[]},checks:{partial:true,passed:true,warnings:[]},context:{match_id:'match',hall_id:'hall',camera:{},units:{},pitch:{length_m:40,width_m:20},teams:{home:{id:'team1',name:'Север'},away:{id:'team2',name:'Юг'}},rosters:[{player_id:'person',side:'home',display_name:'Иван Петров',shirt_number:'7'}]},side_map:{A:'home',B:'away'},tracks:[{track_id:1,team:'A',role:'player',intervals:[[0,60]],thumb:null,has_metrics:false}],assignments:[],players:[]} as AnalysisRun;
beforeEach(()=>{localStorage.clear();vi.clearAllMocks()});
it('shows partial recording and unknown measurements without invented zero',()=>{
 render(<MemoryRouter><AnalysisReport partial players={[{player_id:'person',display_name:'Иван',shirt_number:'7',side:'home',metrics:{distance_m:null,observed_s:60,m_per_min:null,hsr_m:null,sprints:null,vmax_ms:null,heatmap_s:null}}]} /></MemoryRouter>);
 expect(screen.getByText('Частичная запись')).toBeVisible();expect(screen.getByText('Время в анализируемом видео')).toBeVisible();expect(screen.getByText('Нет данных')).toBeVisible();expect(screen.queryByText('Игровое время')).toBeNull();
});
it('retains identity input and short fragments after failed saving and remount',async()=>{
 const save=vi.fn().mockRejectedValue(new Error('Ошибка связи'));
 const view=render(<MemoryRouter><IdentityReview run={run} actorId="actor" editable onSave={save}/></MemoryRouter>);
 fireEvent.change(screen.getByLabelText('Игрок фрагмента 1'),{target:{value:'person'}});fireEvent.click(screen.getByRole('button',{name:'Сохранить сопоставление'}));
 await waitFor(()=>expect(save).toHaveBeenCalled());view.unmount();
 render(<MemoryRouter><IdentityReview run={run} actorId="actor" editable onSave={save}/></MemoryRouter>);
 expect(screen.getByLabelText('Игрок фрагмента 1')).toHaveValue('person');expect(screen.getByText('Короткий фрагмент · метрик нет')).toBeVisible();
});
it('ordinary administrator cannot start import or job',async()=>{
 vi.mocked(api).mockResolvedValue({match_id:'match',analysis_revision:0,active_run_id:null,published_run_id:null,jobs:[],runs:[]});
 render(<MemoryRouter><VideoAnalysisTab matchId="match" actorId="actor" canManage={false}/></MemoryRouter>);
 await screen.findByText('Отчётов пока нет');expect(screen.queryByRole('button',{name:'Создать задание'})).toBeNull();expect(screen.queryByLabelText('Пакет результата ZIP')).toBeNull();
});
it('retries the exact command after a successful response body is lost',async()=>{
 vi.mocked(api).mockRejectedValueOnce(new ApiError('network','Ответ потерян')).mockResolvedValueOnce(run);
 const body={expected_revision:0};await expect(sendJson('retry','/matches/match/analysis/runs/run/confirm',body)).rejects.toThrow();
 const pending=readPending('retry')!;expect(pending.body.request_id).toBeTruthy();
 await sendJson('retry','/matches/match/analysis/runs/run/confirm',body);
 expect(vi.mocked(api).mock.calls[0]).toEqual(vi.mocked(api).mock.calls[1]);expect(readPending('retry')).toBeNull();
});
it('conflict preserves pending payload instead of silently rebasing',async()=>{
 vi.mocked(api).mockRejectedValue(new ApiError('conflict','Обновите версию',{},1,409));
 await expect(sendJson('conflict','/x',{expected_revision:0})).rejects.toThrow();
 await expect(sendJson('conflict','/x',{expected_revision:1})).rejects.toThrow();
 expect(vi.mocked(api)).toHaveBeenCalledTimes(1);expect(readPending('conflict')!.body.expected_revision).toBe(0);
});

it('shows track and team period measurements before identity confirmation',async()=>{
 const preview={...run,checks:{...run.checks,critical_errors:[]},report:{...run.report,periods:[{key:'all',name:'Весь матч',teams:{A:{distance_m:120,low_data:false},B:{distance_m:null,low_data:true,metric_notes:{distance_m:'Нет наблюдений команды'}}},players:[{track_id:1,label:'Фрагмент 1',team:'A',role:'player',distance_m:120,observed_s:60,m_per_min:120,hsr_m:0,sprints:0,vmax_ms:2,heatmap_s:null}]}]},manifest:{...run.manifest,primary_period_key:'all'}};
 const overview={match_id:'match',analysis_revision:0,active_run_id:null,published_run_id:null,jobs:[],runs:[run]};
 vi.mocked(api).mockImplementation(async path=>String(path).endsWith('/team-review-tasks')?{items:[],total:0}:String(path).endsWith('/team-confirmations')?{workflow:'admin',sides:[]}:String(path).endsWith('/runs/run')?preview:overview);
 render(<MemoryRouter><VideoAnalysisTab matchId="match" actorId="actor" canManage/></MemoryRouter>);
 // Предварительные показатели свёрнуты, чтобы не отодвигать сопоставление треков.
 const summary=await screen.findByText('Предварительные показатели записи');expect(screen.getByRole('heading',{name:'Командные показатели по периодам'})).not.toBeVisible();
 fireEvent.click(summary);
 expect(screen.getByRole('heading',{name:'Командные показатели по периодам'})).toBeVisible();expect(screen.getByRole('heading',{name:'Показатели фрагментов до сопоставления'})).toBeVisible();expect(screen.getByText('Нет наблюдений команды')).toBeVisible();
});
it('tells which rating versions the confirmed video produced',async()=>{
 const confirmed={...run,status:'confirmed',checks:{...run.checks,critical_errors:[]},auto_sources:{participation_version_id:'p',participation_revision:2,players:7,action_version_id:'a',action_revision:3,passes:41,note:null}};
 const overview={match_id:'match',analysis_revision:0,active_run_id:'run',published_run_id:null,jobs:[],runs:[{...run,status:'confirmed'}]};
 vi.mocked(api).mockImplementation(async path=>String(path).endsWith('/team-review-tasks')?{items:[],total:0}:String(path).endsWith('/team-confirmations')?{workflow:'admin',sides:[]}:String(path).endsWith('/runs/run')?confirmed:overview);
 render(<MemoryRouter><VideoAnalysisTab matchId="match" actorId="actor" canManage/></MemoryRouter>);
 expect(await screen.findByText(/Для оценок создано автоматически/)).toHaveTextContent('участие №2 — время на площадке у 7 игроков, действия №3 — 41 передача');
 expect(screen.getByRole('link',{name:'участие №2'})).toHaveAttribute('href','?tab=participation');
});
