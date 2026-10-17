import {describe,expect,it} from 'vitest';
import type {AnalysisOverview,Match,Version} from '../../api/domain';
import type {Analytics} from '../ratings/types';
import {cvBlock,protocolBlock,ratingBlock} from './publicationModel';

const match={published_version_id:'v2'} as Match;
const versions=[{id:'v3',number:3,confirmed_at:'2026-10-20T19:05:00Z',published_at:null},{id:'v2',number:2,confirmed_at:'2026-10-20T18:00:00Z',published_at:'2026-10-20T18:14:00Z'}] as Version[];
describe('publication blocks',()=>{
 it('describes each source separately',()=>{
  const p=protocolBlock(match,versions,'v3');
  expect(p.currentLabel).toMatch(/^версия 2/);expect(p.selectedLabel).toMatch(/^версия 3/);expect(p.blockers).toEqual([]);
  expect(p.changeSummary).toMatch(/Счёт, события и состав/);
  expect(protocolBlock(match,versions,'v2').changeSummary).toBe('Выбранная версия уже на сайте');
  expect(protocolBlock({published_version_id:null} as Match,[],null).blockers[0].href).toBe('?tab=protocol');
 });
 it('blocks CV without a confirmed run and links to review',()=>{
  const overview={published_run_id:'r1',runs:[{id:'r1',status:'confirmed',passed:true,partial:true,created_at:'2026-10-20T18:00:00Z'},{id:'r3',status:'review',passed:true,partial:true}]} as AnalysisOverview;
  expect(cvBlock(overview,'r3').currentLabel).toMatch(/^от \d+ окт\..* · фрагмент$/);
  expect(cvBlock(overview,'r3').blockers).toContainEqual({text:'Выбранная версия ещё не подтверждена',href:'?tab=review&run_id=r3'});
  expect(cvBlock({published_run_id:null,runs:[{id:'r3',status:'review'}]} as AnalysisOverview,'r3').blockers[0]).toEqual({text:'Версия на проверке не подтверждена',href:'?tab=review'});
 });
 it('keeps the published edition until a new one is explicitly published',()=>{
  const analytics={public_snapshot_id:'B',policy_approved:true,snapshots:[
   {snapshot_id:'B',scope:'public',calculated_at:'2026-10-20T10:00:00Z',published_at:'2026-10-20T10:05:00Z',stale:true},
   {snapshot_id:'C',scope:'public',calculated_at:'2026-10-21T10:00:00Z',published_at:null,stale:false}]} as unknown as Analytics;
  const r=ratingBlock(analytics,'t1');
  expect(r.currentLabel).toMatch(/^опубликован \d+ окт\./);expect(r.selectedLabel).toMatch(/^новый расчёт от/);expect(r.candidate?.snapshot_id).toBe('C');
  expect(r.blockers[0].text).toMatch(/Источники изменились/);
 });
});
