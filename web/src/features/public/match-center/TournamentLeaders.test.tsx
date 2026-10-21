import {afterEach,it,expect,vi} from 'vitest';
import {render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {TournamentLeaders} from './TournamentLeaders';
afterEach(()=>vi.unstubAllGlobals());
it('uses one qualified public edition and preserves canonical tied ranks in links',async()=>{
 const requests:string[]=[];vi.stubGlobal('fetch',vi.fn(async input=>{requests.push(String(input));return new Response(JSON.stringify({snapshot_id:'edition',published_at:'2026-10-18T10:00:00Z',items:[1,2].map(n=>({player_id:`p${n}`,display_name:`Игрок ${n}`,rank:1,display_rating:8.2,rated_match_count:5,qualification:'qualified',teams:[{name:'Север'}]}))}))}));
 render(<MemoryRouter><TournamentLeaders tournamentId="t"/></MemoryRouter>);
 expect(await screen.findByRole('link',{name:'Игрок 1'})).toHaveAttribute('href','/watch/players/p1?tournament_id=t&snapshot_id=edition');
 expect(screen.getByRole('link',{name:'Весь рейтинг'})).toHaveAttribute('href','/watch/tournaments/t?tab=ratings&snapshot_id=edition');expect(requests).toEqual(['/api/v1/public/tournaments/t/ratings?qualification=qualified&limit=5&offset=0']);
 expect(screen.getAllByText('1')).toHaveLength(2);
});
