import {describe,expect,it} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import type {PublicProtocol,TeamActionStats} from '../../api/domain';
import {ShotMap} from '../../components/pitch/ShotMap';
import {actionLines,leader,protocolLines} from './stats';
import {periodOptions} from './MatchStats';
import type {ReportModel} from './model';
import {StatRow} from './StatBlocks';
import {MatchTimeline,eventMinute,goalScorers} from './MatchTimeline';

const P1='p1',P2='p2';
const protocol={number:1,regulation:{total_s:2400,rules:{periods_s:[1200,1200],shootout:{enabled:false}}},
 lineup:[{player_id:P1,display_name:'Иван',shirt_number:'7',side:'home'},{player_id:P2,display_name:'Пётр',shirt_number:'9',side:'away'}],
 protocol:{completeness:{goals:'complete',assists:'complete',fouls:'partial',cards:'complete',lineup:'complete',time:'complete'},
  events:[{id:'g1',kind:'goal',side:'home',period:1,elapsed_ms:300000,player_id:P1,own_goal:false,from_penalty:false,assist_known:false},
   {id:'g2',kind:'goal',side:'away',period:2,elapsed_ms:60000,player_id:P1,own_goal:true,from_penalty:false,assist_known:false},
   {id:'f1',kind:'foul',side:'away',period:2,elapsed_ms:70000,player_id:P2,accumulated:true},
   {id:'c1',kind:'card',side:'away',period:2,elapsed_ms:80000,player_id:P2,card:'yellow'}]},
 projection:{effective_score:{home:2,away:0},period_event_scores:{'1':{home:1,away:0},'2':{home:1,away:0}},
  effective_totals:{home:{fouls:null,yellow_cards:0,dismissals:0},away:{fouls:null,yellow_cards:1,dismissals:0}},
  accumulated_fouls:{home:{},away:{'2':1}},incomplete_sections:['fouls']}} as unknown as PublicProtocol;

describe('match statistics',()=>{
 it('marks the better value and lower-is-better discipline',()=>{
  const lines=protocolLines(protocol,'all');
  expect(leader(lines.find(l=>l.key==='goals')!)).toBe('home');
  expect(leader(lines.find(l=>l.key==='yellow')!)).toBe('home');
  // Фолы не подтверждены полностью: показываются известные, с пометкой.
  const fouls=lines.find(l=>l.key==='fouls')!;
  expect(fouls.away).toEqual({value:1,text:'1',note:'известные'});expect(fouls.partial).toBe(true);
 });
 it('counts a period from its own events and shows accumulated fouls',()=>{
  const lines=protocolLines(protocol,'2');
  expect(lines.find(l=>l.key==='goals')!.home.value).toBe(1);
  expect(lines.find(l=>l.key==='accumulated')!.away.value).toBe(1);
 });
 it('formats percent with numerator, denominator and unknown outcomes, never 0 % without attempts',()=>{
  const stats={rows:[{key:'passes_accurate',label:'Точные передачи',group:'passes',category:'passes',unit:'percent',coverage:'partial',
   home:{value:66.7,numerator:2,denominator:3,unknown:1},away:{value:null,numerator:0,denominator:0,unknown:0}}]} as unknown as TeamActionStats;
  const line=actionLines(stats).passes[0];
  expect(line.home.text).toBe('2/3 (67 %)');expect(line.home.note).toBe('ещё неизвестно: 1');
  expect(line.away.text).toBe('—');expect(line.partial).toBe(true);
  render(<StatRow line={line}/>);
  expect(screen.getByText('2/3 (67 %)').className).toBe('');
 });
 it('marks automatic video passes instead of the manual-markup asterisk and keeps protocol periods',()=>{
  const stats={source:{kind:'cv_auto'},periods:[{key:'all',label:'Весь матч'}],rows:[{key:'passes_total',label:'Передачи',group:'passes',
   category:'passes',unit:'count',coverage:'partial',source:'cv_auto',home:{value:12,numerator:null,denominator:null,unknown:0},
   away:{value:9,numerator:null,denominator:null,unknown:0}}]} as unknown as TeamActionStats;
  const line=actionLines(stats).passes[0];
  expect(line.auto).toBe(true);expect(line.partial).toBe(false);
  render(<StatRow line={line}/>);
  expect(screen.getByText('авто')).toHaveAttribute('title',expect.stringContaining('распознаётся не каждая передача'));
  expect(screen.queryByText('*')).toBeNull();
  const model={actions:{status:'ready',value:stats},protocol:{status:'ready',value:protocol},cv:{status:'absent'}} as unknown as ReportModel;
  expect(periodOptions(model).map(p=>p.key)).toEqual(['all','1','2']);
 });
 it('builds scorers on the scoring side and a two-sided timeline with score after each goal',()=>{
  expect(eventMinute(protocol,protocol.protocol.events[1])).toBe("22'");
  const scorers=goalScorers(protocol);
  expect(scorers.home.map(s=>s.note)).toEqual([null,'автогол']);expect(scorers.away).toEqual([]);
  render(<MatchTimeline value={protocol}/>);
  expect(screen.getByText('Гол · 2 : 0')).toBeInTheDocument();
  expect(screen.getByText('Конец 1-го тайма · 1 : 0')).toBeInTheDocument();
 });
 it('selects a shot and describes it without inventing xG',()=>{
  render(<ShotMap lengthM={40} widthM={20} homeName="Север" awayName="Юг" shots={[
   {id:'s1',side:'home',x:30,y:10,goal:true,on_target:true,blocked:false,outcome:'goal',start_ms:300000,player:'Иван'},
   {id:'s2',side:'away',x:8,y:5,goal:false,on_target:false,blocked:false,outcome:'off_target',start_ms:1300000,player:null}]}/>);
  expect(screen.getByText("6' · Иван · Гол")).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Юг: Мимо ворот'}));
  expect(screen.getByText("22' · Юг · Мимо ворот")).toBeInTheDocument();
  expect(screen.queryByText(/xG/)).toBeNull();
 });
});
