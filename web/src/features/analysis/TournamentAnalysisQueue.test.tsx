import {test,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {MemoryRouter,Routes,Route,useLocation} from 'react-router-dom';
import {TournamentAnalysisQueue} from './TournamentAnalysisQueue';
afterEach(()=>vi.unstubAllGlobals());
test('filters review work and preserves the queue context when opening a match',async()=>{
 const requests:string[]=[];let state:unknown;
 vi.stubGlobal('fetch',vi.fn(async input=>{requests.push(String(input));return new Response(JSON.stringify({items:[{match_id:'match',home_name:'Север',away_name:'Юг',scheduled_at:'2026-10-20T16:00:00Z',run_id:'run',status:'review',unresolved:0,reason:'Игроки подтверждены',teams:[{side:'home',status:'team_confirmed',actor_kind:'captain'},{side:'away',status:'team_confirmed',actor_kind:'captain'}],next_action:{label:'Технически подтвердить',href:'/matches/match?tab=review&run_id=run'}}],total:1}))}));
 function Target(){state=useLocation().state;return null}
 render(<MemoryRouter initialEntries={['/tournaments/tour?tab=analysis']}><Routes><Route path="/tournaments/:id" element={<TournamentAnalysisQueue tournamentId="tour"/>}/><Route path="/matches/:id" element={<Target/>}/></Routes></MemoryRouter>);
 await screen.findByText('Север — Юг');fireEvent.change(screen.getByLabelText('Состояние обработки'),{target:{value:'review'}});await waitFor(()=>expect(requests.some(p=>p.includes('status=review'))).toBe(true));fireEvent.click(await screen.findByRole('link',{name:'Технически подтвердить'}));expect(state).toEqual({analysisReturn:'/tournaments/tour?tab=analysis&status=review'});
});
