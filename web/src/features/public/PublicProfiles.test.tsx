import {test,expect,vi,afterEach} from 'vitest';
import {render,screen} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {PublicTeamPage} from './PublicTeamPage';
import {PublicPlayerPage} from './PublicPlayerPage';
vi.mock('../ratings/PlayerRatingHistory',()=>({PlayerRatingHistory:()=> <p>Рейтинг в этом турнире пока не доступен.</p>}));
afterEach(()=>vi.unstubAllGlobals());
const tid='11111111-1111-4111-8111-111111111111',team='22222222-2222-4222-8222-222222222222',pid='33333333-3333-4333-8333-333333333333';
test('a team without a published protocol shows schedule and an honest empty roster',async()=>{
 vi.stubGlobal('fetch',vi.fn(async input=>new Response(JSON.stringify(String(input).includes('/matches')?{items:[],total:0}:{id:team,name:'Север',tournament:{id:tid,name:'Кубок',timezone:'Europe/Moscow'},players:{items:[],total:0}}))));
 render(<MemoryRouter initialEntries={[`/watch/tournaments/${tid}/teams/${team}`]}><Routes><Route path="/watch/tournaments/:id/teams/:teamId" element={<PublicTeamPage/>}/></Routes></MemoryRouter>);
 await screen.findByRole('heading',{name:'Север'});expect(screen.getByText('Состав ещё не опубликован')).toBeInTheDocument();expect(screen.getByRole('heading',{name:'Матчи команды'})).toBeInTheDocument();
});
test('a player with a published lineup opens even without a rating',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({id:pid,display_name:'Иван из протокола',teams:{items:[{team_id:team,team_name:'Север',tournament_id:tid,tournament_name:'Кубок'}],total:1},appearances:{items:[{match_id:team,display_name:'Иван из протокола',shirt_number:'7',team_id:team,team_name:'Север',tournament_id:tid,tournament_name:'Кубок',scheduled_at:'2026-10-20T16:00:00Z',timezone:'Europe/Moscow'}],total:1}}))));
 render(<MemoryRouter initialEntries={[`/watch/players/${pid}?tournament_id=${tid}`]}><Routes><Route path="/watch/players/:id" element={<PublicPlayerPage/>}/></Routes></MemoryRouter>);
 await screen.findByRole('heading',{name:'Иван из протокола'});expect(screen.getByRole('heading',{name:'Опубликованные выступления'})).toBeInTheDocument();expect(screen.getByText('Рейтинг в этом турнире пока не доступен.')).toBeInTheDocument();
});
