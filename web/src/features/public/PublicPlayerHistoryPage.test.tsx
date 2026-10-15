import {afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import {PlayerRatingHistory} from '../ratings/PlayerRatingHistory';
import {RankingTable} from '../ratings/TournamentRatings';
import {PublicPlayerHistoryPage} from './PublicPlayerHistoryPage';
import type {RatingSummary} from '../ratings/types';

const P='33333333-3333-4333-8333-333333333333',T='88888888-8888-4888-8888-888888888888',S='77777777-7777-4777-8777-777777777777';
afterEach(()=>vi.unstubAllGlobals());

describe('public rating history',()=>{
 it('requests the selected edition without requesting private history',async()=>{
  const paths:string[]=[];
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{
    paths.push(String(input));
    return new Response(JSON.stringify({snapshot_id:'edition-A',summary:[],matches:[]}));
  }));
  render(<MemoryRouter><PlayerRatingHistory playerId="p1" publicView
    initialTournament="t1" initialSnapshot="edition-A"/></MemoryRouter>);
  await waitFor(()=>expect(paths.some(p=>p.includes('/public/players/p1/ratings')&&
    p.includes('snapshot_id=edition-A'))).toBe(true));
  expect(paths.every(p=>p.includes('/public/'))).toBe(true);
 });
 it('names the player from published rows and keeps tournament and edition in the URL',async()=>{
  const paths:string[]=[];let search='';
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{
   const path=String(input);paths.push(path);
   if(path.includes('/public/tournaments'))return new Response(JSON.stringify({items:[{id:T,name:'Кубок',season:'2026'}],total:1}));
   return new Response(JSON.stringify({snapshot_id:S,summary:[{player_id:P,display_name:'Игрок из издания',rank:1}],matches:[]}));
  }));
  function Probe(){search=useLocation().search;return null}
  render(<MemoryRouter initialEntries={[`/watch/players/${P}?tournament_id=${T}&snapshot_id=${S}`]}><Routes>
   <Route path="/watch/players/:id" element={<><PublicPlayerHistoryPage/><Probe/></>}/></Routes></MemoryRouter>);
  expect(await screen.findByRole('heading',{level:1,name:'Игрок из издания'})).toBeInTheDocument();
  expect(new URLSearchParams(search).get('snapshot_id')).toBe(S);
  expect(new URLSearchParams(search).get('tournament_id')).toBe(T);
  expect(paths.every(p=>p.startsWith('/api/v1/public/'))).toBe(true);
  expect(paths.some(p=>p.includes('/auth/'))).toBe(false);
 });
 it('links public rankings to the public history with the same edition',()=>{
  render(<MemoryRouter><RankingTable rows={[{player_id:P,display_name:'Игрок',rank:1} as unknown as RatingSummary]} publicView tournamentId={T} snapshotId={S}/></MemoryRouter>);
  expect(screen.getByRole('link',{name:'Игрок'})).toHaveAttribute('href',`/watch/players/${P}?tournament_id=${T}&snapshot_id=${S}`);
 });
});
