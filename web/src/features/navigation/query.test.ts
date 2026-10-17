import {describe,expect,it} from 'vitest';
import {isUuid,patchQuery,readMatchTab,scheduleReturn,analysisQueueReturn} from './query';

describe('match URL context',()=>{
 it('restores only the same local tournament schedule',()=>{
  expect(scheduleReturn('/tournaments/t1?tab=matches&day=2026-10-20&hall_id=h1&status=ended&view=grid','t1')).toBe('/tournaments/t1?tab=matches&day=2026-10-20&hall_id=h1&status=ended&view=grid');
  for(const target of ['https://other.test/tournaments/t1','//other.test','/tournaments/t2?tab=matches','javascript:alert(1)'])expect(scheduleReturn(target,'t1')).toBe('/tournaments/t1?tab=matches');
 });
 it('returns to a filtered local analysis queue and rejects external or foreign context',()=>{
  expect(analysisQueueReturn('/tournaments/t1?tab=analysis&status=review&offset=25','t1')).toBe('/tournaments/t1?tab=analysis&status=review&offset=25');
  for(const v of [null,'https://other.test/tournaments/t1?tab=analysis','/tournaments/t2?tab=analysis','/tournaments/t1?tab=matches'])expect(analysisQueueReturn(v,'t1')).toBeNull();
 });
 it('changes a section without discarding edition, player and tournament context',()=>{
  const next=patchQuery(new URLSearchParams('snapshot_id=A&player_id=P&tab=stats'),{tab:'players'});
  expect(next.get('snapshot_id')).toBe('A');
  expect(next.get('player_id')).toBe('P');
  expect(readMatchTab(new URLSearchParams('tab=private'),'public')).toBe('overview');
  expect(isUuid('not-a-uuid')).toBe(false);
 });
 it('clones the source and removes null keys',()=>{
  const source=new URLSearchParams('tab=players&player_id=P');
  const next=patchQuery(source,{player_id:null,filter:'unassigned'});
  expect(source.get('player_id')).toBe('P');
  expect(next.has('player_id')).toBe(false);
  expect(next.get('filter')).toBe('unassigned');
 });
 it('normalizes tabs for each audience and keeps old private links',()=>{
  for(const tab of ['overview','events','players','stats','video'])expect(readMatchTab(new URLSearchParams({tab}),'public')).toBe(tab);
  expect(readMatchTab(new URLSearchParams('tab=publication'),'public')).toBe('overview');
  expect(readMatchTab(new URLSearchParams(),'private')).toBe('overview');
  expect(readMatchTab(new URLSearchParams('tab=analysis'),'private')).toBe('review');
  expect(readMatchTab(new URLSearchParams('tab=video'),'private')).toBe('review');
  expect(readMatchTab(new URLSearchParams('tab=history'),'private')).toBe('history');
  expect(readMatchTab(new URLSearchParams('tab=../x'),'private')).toBe('overview');
 });
 it('accepts only canonical UUIDs',()=>{
  expect(isUuid('5b1e2c3d-4e5f-4a6b-8c7d-9e0fa1b2c3d4')).toBe(true);
  expect(isUuid('5B1E2C3D-4E5F-4A6B-8C7D-9E0FA1B2C3D4')).toBe(true);
  expect(isUuid(null)).toBe(false);
  expect(isUuid('5b1e2c3d4e5f4a6b8c7d9e0fa1b2c3d4')).toBe(false);
 });
});
