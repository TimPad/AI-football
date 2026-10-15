import {describe,expect,it} from 'vitest';
import type {ReportContext} from './model';
import {canAttachCurrentCv,mergeRoster,periodLabel,publicAnalysisFromRun} from './adapters';
import type {AnalysisRun,PublicAnalysis,PublicProtocol,MatchRatingsView} from '../../api/domain';

const lineup=(player_id:string,display_name:string,shirt_number:string|null,side:'home'|'away')=>({player_id,display_name,shirt_number,side});
const metrics=(distance_m:number|null)=>({distance_m,observed_s:60,m_per_min:null,hsr_m:0,sprints:0,vmax_ms:null,heatmap_s:null});

describe('report sources',()=>{
 it('does not relabel current CV as the source of a rating',()=>{
  const c:ReportContext={matchId:'m',protocolPublicId:'p',cvRunId:'B',
    ratingSnapshotId:'A',historicalRating:true,periodKey:'all'};
  expect(canAttachCurrentCv(c,'rating')).toBe(false);
  expect(canAttachCurrentCv(c,'cv')).toBe(true);
  expect(canAttachCurrentCv({...c,cvRunId:null},'cv')).toBe(false);
  expect(periodLabel('all','Весь матч',true)).toBe('Обработанный фрагмент');
  expect(periodLabel('all','Весь матч',false)).toBe('Весь матч');
  expect(periodLabel('h1','1-й тайм',true)).toBe('1-й тайм');
 });
});

describe('roster adapter',()=>{
 const teams={home:'team-h',away:'team-a'};
 it('joins sources by player UUID and keeps equal names apart',()=>{
  const protocol={lineup:[lineup('u1','Иван Петров','7','home'),lineup('u2','Иван Петров','7','away')]} as unknown as PublicProtocol;
  const cv={players:[{player_id:'u2',display_name:'Петров',shirt_number:'9',side:'away',metrics:metrics(0)},
    {player_id:'u3',display_name:'Новый',shirt_number:'7',side:'home',metrics:metrics(null)}]} as unknown as PublicAnalysis;
  const ratings={snapshot_id:'A',items:[{player_id:'u1',display_name:'Иван Петров',team_id:'team-h',role:'ala',display_rating:7.2}]} as unknown as MatchRatingsView;
  const rows=mergeRoster({protocol,cv,ratings,teams});
  expect(rows.map(r=>r.playerId)).toEqual(['u1','u3','u2']);
  const byId=Object.fromEntries(rows.map(r=>[r.playerId,r]));
  expect(byId.u1.sources).toEqual(['protocol','rating']);
  expect(byId.u1.rating?.role).toBe('ala');
  expect(byId.u2.sources).toEqual(['protocol','cv']);
  expect(byId.u2.name).toBe('Иван Петров');
  expect(byId.u2.shirtNumber).toBe('7');
  expect(byId.u2.cv?.metrics.distance_m).toBe(0);
  expect(byId.u3.sources).toEqual(['cv']);
  expect(byId.u3.cv?.metrics.distance_m).toBeNull();
  expect(byId.u3.side).toBe('home');
 });
 it('does not guess a side for a rating row of an unknown team',()=>{
  const ratings={snapshot_id:'A',items:[{player_id:'u9',display_name:'X',team_id:'other',role:'ala'}]} as unknown as MatchRatingsView;
  expect(mergeRoster({protocol:null,cv:null,ratings,teams})[0].side).toBeNull();
 });
});

describe('private run adapter',()=>{
 it('keeps only the public whitelist of a private run',()=>{
  const run={id:'r',match_id:'m',side_map:{A:'home'},partial:true,
   context:{teams:{A:{id:'t',name:'Север'}},pitch:{}},
   manifest:{primary_period_key:'all',source_video:{duration_s:300}},
   report:{match:{processed_s:186},pitch:{length_m:41,width_m:15.5,cell_m:1,secret:1},
     periods:[{key:'all',name:'Весь матч',duration_s:186,secret:2,teams:{A:{distance_m:10,observed_s:0,heatmap_s:[[0]],private_note:'x'}}}]},
   players:[{player_id:'u1',display_name:'И',shirt_number:null,side:'home',track_ids:[4],metrics:{distance_m:5,notes:'private'}}],
   tracks:[{id:4}],assignments:[]} as unknown as AnalysisRun;
  const value=publicAnalysisFromRun(run);
  expect(value.pitch).toEqual({length_m:41,width_m:15.5,cell_m:1,orientation:'camera'});
  expect(value.processed_s).toBe(186);
  expect(value.video_s).toBe(300);
  expect(JSON.stringify(value)).not.toMatch(/secret|private|track_ids/);
  expect(value.players[0].metrics.distance_m).toBe(5);
  expect(value.players[0].metrics.observed_s).toBeNull();
 });
});
