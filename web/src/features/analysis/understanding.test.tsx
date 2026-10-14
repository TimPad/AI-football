import {beforeEach,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {MatchUnderstanding} from './MatchUnderstanding';
import {IdentityReview} from './IdentityReview';
import {AnalysisTab} from './AnalysisTab';
import type {AnalysisRun} from '../../api/domain';
import type {UnderstandingView} from './understandingTypes';
vi.mock('../../api/client',async()=>({...await vi.importActual<typeof import('../../api/client')>('../../api/client'),api:vi.fn()}));
import {api} from '../../api/client';
const run={id:'run',match_id:'match',revision:0,status:'review',side_map:{A:'home',B:'away'},tracks:[{track_id:1,team:'A',role:'player',intervals:[[0,60]],has_metrics:false}],assignments:[],players:[],context:{teams:{home:{name:'Север'},away:{name:'Юг'}},rosters:[{player_id:'person',side:'home',display_name:'Иван Петров',shirt_number:'7'}]}} as unknown as AnalysisRun;
const event={id:'e1',kind:'goal_candidate',start_ms:1000,end_ms:2000,team:'A',track_ids:[1],evidence_ids:['f1'],audio_observations:[],limitations:['Мяч закрыт']};
const value={run_id:'run',match_id:'match',revision:0,status:'review',side_map_verified:true,reviews:{},history:[],effective_events:[event],verified_summary:[],identity_suggestions:[],understanding:{source:{analysis_scope:'highlights'},coverage:{status:'partial',covered_intervals:[[0,2000]],unknown_intervals:[[2000,5000]]},evidence:[{id:'f1',frame_id:25,video_ms:1000,crop:null}],events:[event],states:[{kind:'unknown',start_ms:2000,end_ms:5000,limitations:['Не видно']}],phases:[],summary:[{text:'<img src=x onerror=alert(1)>',event_ids:['e1'],metric_refs:[]}]}} as unknown as UnderstandingView;
beforeEach(()=>{localStorage.clear();vi.clearAllMocks()});
function show(data:UnderstandingView|null=value,editable=true,onChanged=vi.fn()){return render(<MatchUnderstanding value={data} run={run} actorId="actor" editable={editable} onChanged={onChanged}/>)}
it('keeps a legacy report usable without episodes',()=>{show(null);expect(screen.getByText(/В этой версии нет анализа эпизодов/)).toBeVisible()});
it('shows scope, unknown time and escaped hypotheses without a video player',()=>{
 const view=show();fireEvent.click(screen.getByText(/Необработанные интервалы/));fireEvent.click(screen.getByText('Предположения по записи'));expect(screen.getByText('Нарезка моментов')).toBeVisible();expect(screen.getByText(/Не обработано: 00:02–00:05/)).toBeVisible();expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible();expect(view.container.querySelector('video')).toBeNull();expect(view.container.querySelector('img[src="x"]')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Кадры эпизода e1'}));expect(screen.getByAltText('Кадр 25 · 00:01')).toHaveAttribute('src','/api/v1/matches/match/analysis/runs/run/understanding/evidence/f1');
});
it('never auto-selects a suggested player and hides a stale side hint',()=>{
 render(<MemoryRouter><IdentityReview run={run} actorId="actor" editable onSave={vi.fn()} suggestions={[{track_id:1,player_id:'person',number:'7',status:'candidate',reasons:['Проверить'],evidence_ids:['f1']}]}/></MemoryRouter>);
 expect(screen.getByLabelText('Игрок фрагмента 1')).toHaveValue('');expect(screen.getByText(/Предположение: №7 · Иван Петров/)).toBeVisible();
 fireEvent.change(screen.getByLabelText('Команда A на видео'),{target:{value:'away'}});expect(screen.queryByText(/Предположение: №7 · Иван Петров/)).toBeNull();expect(screen.getByText(/Сохраните стороны/)).toBeVisible();
});
it('preserves a correction after network loss and retries the exact frozen command',async()=>{
 vi.mocked(api).mockRejectedValueOnce(Error('Ответ потерян')).mockResolvedValueOnce({...value,revision:1});const changed=vi.fn();const view=show(value,true,changed);
 fireEvent.click(screen.getByRole('button',{name:'Исправить эпизод e1'}));fireEvent.change(screen.getByLabelText('Тип эпизода'),{target:{value:'shot_candidate'}});fireEvent.change(screen.getByLabelText('Причина решения'),{target:{value:'Удар мимо'}});fireEvent.click(screen.getByRole('button',{name:'Сохранить решение'}));
 await screen.findByText('Ответ потерян');view.unmount();show(value,true,changed);expect(screen.getByLabelText('Причина решения')).toHaveValue('Удар мимо');
 fireEvent.click(screen.getByRole('button',{name:'Повторить решение'}));await waitFor(()=>expect(changed).toHaveBeenCalled());expect(vi.mocked(api).mock.calls[0]).toEqual(vi.mocked(api).mock.calls[1]);const body=JSON.parse(String(vi.mocked(api).mock.calls[0][1]?.body));expect(body.expected_revision).toBe(0);expect(body.correction.kind).toBe('shot_candidate');expect(body.request_id).toBeTruthy();
});
it('does not silently rebase a stale correction',async()=>{
 const view=show();fireEvent.click(screen.getByRole('button',{name:'Исправить эпизод e1'}));view.unmount();show({...value,revision:2});expect(screen.getByText(/Версия изменилась/)).toBeVisible();expect(screen.getByRole('button',{name:'Сохранить решение'})).toBeDisabled();
});
it('shows current verified summary, rejection and immutable confirmed review',()=>{
 show({...value,status:'confirmed',reviews:{e1:{decision:'rejected'}},effective_events:[],verified_summary:[{text:'Проверенный эпизод',event_ids:['e2'],player_ids:[]}]},false);
 expect(screen.getByText('Проверенный эпизод')).toBeVisible();expect(screen.getByText('Отклонён')).toBeVisible();expect(screen.queryByRole('button',{name:'Принять эпизод e1'})).toBeNull();
});
it('ordinary admin never requests closed understanding even for a v2 report',async()=>{
 const preview={...run,manifest:{source_video:{duration_s:240}},report:{match:{processed_s:120},periods:[]},checks:{critical_errors:[],warnings:[]},passed:true};
 vi.mocked(api).mockImplementation(async path=>String(path).endsWith('/runs/run')?preview:{analysis_revision:0,jobs:[],runs:[{...run,has_understanding:true}]});
 render(<MemoryRouter><AnalysisTab matchId="match" actorId="actor" canManage={false}/></MemoryRouter>);await screen.findByText('На проверке');expect(vi.mocked(api).mock.calls.some(([p])=>String(p).endsWith('/understanding'))).toBe(false);
});
