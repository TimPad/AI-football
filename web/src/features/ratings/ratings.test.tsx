import {describe,it,expect} from 'vitest';
import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {MatchRating} from './MatchRating';
import {RankingTable} from './TournamentRatings';
import type {RatingSummary} from './types';

describe('verified ratings',()=>{
 it('shows missing data without a zero rating',()=>{
  render(<MatchRating value={{score:null,display_rating:null,components:{},reasons:['Недостаточно данных по обороне']}}/>);
  expect(screen.getByText('Недостаточно данных по обороне')).toBeVisible();expect(screen.queryByText('0.0')).toBeNull();
 });
 it('keeps observed zero separate from unknown goalkeeper opportunities',async()=>{
  render(<MatchRating value={{score:null,display_rating:null,role:'goalkeeper',components:{},reasons:[],facts:{recoveries_count:{value:0,numerator:0,denominator:null,unit:'count',completeness:'complete',reason:null},save_pct:{value:null,numerator:0,denominator:0,unit:'percent',completeness:'complete',reason:'no_opportunities'}}}}/>);
  await userEvent.click(screen.getByText('Компоненты и исходные показатели'));
  expect(screen.getByText(/Не было наблюдаемых возможностей/)).toBeVisible();expect(screen.getByText(/Вратарь ·/)).toBeVisible();
 });
 it('renders explanation as text and does not expose private evidence in public',()=>{
  render(<MatchRating publicView value={{score:50,display_rating:5.5,components:{},reasons:[],explanation:{text:'<img src=x onerror=alert(1)>',positive:[{canonical_action_id:'a1',text:'Гол',evidence:[{run_id:'private',evidence_id:'f1'}]}],errors:[]}}}/>);
  expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible();expect(document.querySelector('img')).toBeNull();
 });
 it('shows tied ranks and missing coverage beside scores',()=>{
  const rows=['p1','p2'].map((id)=>({player_id:id,display_name:id,role:null,rank:1,qualification:'qualified',score:65,display_rating:6.9,match_count:3,rated_match_count:3,eligible_play_minutes:30,played_minutes:30,known_played_minutes:30,rated_minutes:30,weight_sum:3,coverage:.8,baseline_influence:.5,facts:{},teams:[],reasons:[]} as RatingSummary));
  render(<MemoryRouter><RankingTable rows={rows}/></MemoryRouter>);
  expect(screen.getAllByText('1')).toHaveLength(2);expect(screen.getAllByText('80%')).toHaveLength(2);
 });
});

import {vi,afterEach} from 'vitest';
import {ParticipationForm,RoleIntervals} from './ParticipationEditor';
import type {Participation,PersonPresence} from './types';
afterEach(()=>{localStorage.clear();vi.unstubAllGlobals()});
function overview():Participation{return {match_id:'m1',match_revision:2,revision:0,current:null,versions:[],lineup:[{player_id:'p1',display_name:'Демо игрок',side:'home'}],rules:{periods_s:[1200,1200]},protocol_versions:[],analysis_runs:[]}}
it('keeps draft and exact request after a lost response',async()=>{
 const sent:string[]=[];let fail=true;vi.stubGlobal('fetch',vi.fn(async(_url,options)=>{sent.push(options.body);if(fail){fail=false;return new Response('{',{status:200})}return new Response(JSON.stringify({id:'version1'}),{status:200})}));
 const saved=vi.fn();const one=render(<ParticipationForm value={overview()} actorId="admin1" onSaved={saved}/>);
 await userEvent.clear(screen.getByLabelText('Длительность шкалы участия, с'));await userEvent.type(screen.getByLabelText('Длительность шкалы участия, с'),'600');
 await userEvent.click(screen.getByRole('button',{name:'Сохранить версию участия'}));
 expect(await screen.findByRole('button',{name:'Повторить отправку'})).toBeVisible();one.unmount();
 render(<ParticipationForm value={overview()} actorId="admin1" onSaved={saved}/>);
 expect(screen.getByLabelText('Длительность шкалы участия, с')).toHaveValue(600);
 await userEvent.click(screen.getByRole('button',{name:'Повторить отправку'}));expect(sent[0]).toBe(sent[1]);expect(saved).toHaveBeenCalledTimes(1);
});
it('retains local input after revision conflict',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({error:{code:'revision_conflict',message:'Версия изменена'}}),{status:409})));
 render(<ParticipationForm value={overview()} actorId="admin1" onSaved={vi.fn()}/>);
 await userEvent.selectOptions(screen.getByLabelText('Полнота участия'),'full_match');await userEvent.click(screen.getByRole('button',{name:'Сохранить версию участия'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Версия изменена');expect(screen.getByLabelText('Полнота участия')).toHaveValue('full_match');
 expect(localStorage.getItem('aifootball:participation-draft:admin1:m1')).toContain('full_match');
});
it('adds a role without inferring presence or position from a catalogue',async()=>{
 const person:PersonPresence={player_id:'p1',presence:null,completeness:'unknown',appeared:null,roles:[]};const change=vi.fn();
 render(<RoleIntervals person={person} duration={600000} onChange={change}/>);
 await userEvent.selectOptions(screen.getByLabelText('Добавляемая роль'),'ala');await userEvent.click(screen.getByRole('button',{name:'Добавить роль'}));
 expect(change).toHaveBeenCalledWith({...person,roles:[{role:'ala',intervals:[]}]});
});
it('preserves malformed nested participation as a recoverable corrupt draft',()=>{
 localStorage.setItem('aifootball:participation-draft:admin1:m1',JSON.stringify({version:1,value:{revision:0,matchRevision:2,document:{clock_basis:'game',duration_ms:2400000,players:[{player_id:'p1',presence:null,completeness:'unknown',appeared:null,roles:null}]}}}));
 expect(()=>render(<ParticipationForm value={overview()} actorId="admin1" onSaved={vi.fn()}/>)).not.toThrow();
 expect(screen.getByRole('alert')).toHaveTextContent('Повреждён черновик');
});
