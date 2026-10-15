import {describe,expect,it} from 'vitest';
import type {AnalysisOverview,AnalysisRun} from '../../api/domain';
import {filteredCount,jobResultState,trackState,visibleTrackIds} from './reviewQueue';

describe('external job status',()=>{
 it('does not claim a new job is ready because an older job has an import',()=>{
  const runs=[{id:'r1',job_id:'j1',status:'confirmed'}] as AnalysisOverview['runs'];
  expect(jobResultState('j1',runs)).toBe('confirmed');
  expect(jobResultState('j2',runs)).toBe('not_uploaded');
  expect(jobResultState('j1',[{...runs[0],status:'review'}])).toBe('review');
 });
 it('treats a job with review and confirmed versions as confirmed, never running',()=>{
  const runs=[{id:'r1',job_id:'j1',status:'review'},{id:'r2',job_id:'j1',status:'confirmed'}] as AnalysisOverview['runs'];
  expect(jobResultState('j1',runs)).toBe('confirmed');
 });
});

describe('track queue',()=>{
 const run={tracks:Array.from({length:51},(_,i)=>({track_id:i+1})),
  assignments:[{track_id:2,player_id:'p'},{track_id:3,excluded_reason:'судья'}]} as unknown as AnalysisRun;
 it('filters and pages only visible ids',()=>{
  expect(visibleTrackIds(run,'all',1,20)).toHaveLength(20);
  expect(visibleTrackIds(run,'all',3,20)).toEqual(Array.from({length:11},(_,i)=>i+41));
  expect(visibleTrackIds(run,'assigned',1,20)).toEqual([2]);
  expect(visibleTrackIds(run,'excluded',1,20)).toEqual([3]);
  expect(filteredCount(run,'unassigned')).toBe(49);
  expect(visibleTrackIds(run,'unassigned',3,20)).toEqual(Array.from({length:9},(_,i)=>i+43));
 });
 it('uses the draft assignments when given and keeps state for hidden rows',()=>{
  const draft=[...run.assignments,{track_id:51,player_id:'q'}];
  expect(trackState(draft,51)).toBe('assigned');
  expect(visibleTrackIds(run,'unassigned',3,20,draft)).not.toContain(51);
  expect(trackState(run.assignments,51)).toBe('unassigned');
 });
});
