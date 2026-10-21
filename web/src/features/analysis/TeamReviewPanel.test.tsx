import {render,screen,waitFor,fireEvent} from '@testing-library/react';
import {test,expect,vi} from 'vitest';
import {TeamReviewPanel} from './TeamReviewPanel';
import type {AnalysisRun} from '../../api/domain';
const execute=vi.hoisted(()=>vi.fn());
vi.mock('../../api/client',()=>({api:vi.fn(async()=>({items:[],total:0}))}));
vi.mock('../ratings/commands',()=>({useRatingCommand:()=>({execute,locked:false}),CommandStatus:()=>null}));
test('asks Admin+ to verify sides before issuing scoped captain tasks',async()=>{
 const run={id:'run',match_id:'match',revision:3,status:'review',side_map_verified:false,context:{teams:{home:{id:'home',name:'Север'},away:{id:'away',name:'Юг'}}}} as unknown as AnalysisRun;
 const view=render(<TeamReviewPanel run={run} actorId="admin" onChanged={()=>{}}/>);await screen.findByText('Сначала проверьте и сохраните соответствие команд A/B ниже.');expect(screen.getByRole('button',{name:'Выдать проверку Север'})).toBeDisabled();
 view.rerender(<TeamReviewPanel run={{...run,side_map_verified:true}} actorId="admin" onChanged={()=>{}}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'Выдать проверку Север'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'Выдать проверку Север'}));expect(execute).toHaveBeenCalledWith('/matches/match/analysis/runs/run/team-review-tasks',{team_id:'home',expected_run_revision:3});
 expect(screen.getByRole('button',{name:'Подтвердить сторону Север как Админ+'})).toBeDisabled();fireEvent.change(screen.getByLabelText('Причина проверки Север'),{target:{value:'Проверено по записи вместо капитана'}});fireEvent.click(screen.getByRole('button',{name:'Подтвердить сторону Север как Админ+'}));expect(execute).toHaveBeenCalledWith('/matches/match/analysis/runs/run/team-confirmations',{side:'home',reason:'Проверено по записи вместо капитана',expected_run_revision:3});
});
