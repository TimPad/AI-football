import {describe,expect,it} from 'vitest';
import type {AnalysisOverview,Match} from '../../api/domain';
import {nextStep} from './MatchOverview';

const match=(extra:Partial<Match>={}):Match=>({id:'m',status:'ended',hall_id:'h',camera_profile_id:'c',lineup:[{}],published_version_id:'v',
 protocol:{draft:false},...extra}) as unknown as Match;
const analysis=(runs:{status:string}[],extra:Partial<AnalysisOverview>={}):AnalysisOverview=>({jobs:[{}],runs,published_run_id:null,...extra}) as unknown as AnalysisOverview;

describe('next step of a match',()=>{
 it('goes through preparation and the protocol first',()=>{
  expect(nextStep(match({hall_id:null}),null).tab).toBe('info');
  expect(nextStep(match({lineup:[]}),null).tab).toBe('lineup');
  expect(nextStep(match({status:'scheduled',protocol:{draft:true} as Match['protocol']}),null).title).toBe('Ведите протокол');
  expect(nextStep(match({protocol:{draft:true} as Match['protocol']}),null).title).toBe('Подтвердите протокол');
  expect(nextStep(match({published_version_id:null}),null)).toMatchObject({title:'Опубликуйте протокол',tab:'publication'});
 });
 it('then leads Admin+ through the video analysis',()=>{
  expect(nextStep(match(),analysis([],{jobs:[]})).title).toBe('Начните видеоанализ');
  expect(nextStep(match(),analysis([])).title).toBe('Загрузите результат обработки');
  expect(nextStep(match(),analysis([{status:'review'}])).title).toBe('Проверьте видеоанализ');
  expect(nextStep(match(),analysis([{status:'confirmed'}]))).toMatchObject({title:'Опубликуйте видеоанализ',tab:'publication'});
  expect(nextStep(match(),analysis([{status:'confirmed'}],{published_run_id:'r'}))).toMatchObject({title:'Матч опубликован',done:true});
 });
 it('needs nothing for a cancelled match or without a camera',()=>{
  expect(nextStep(match({status:'cancelled',hall_id:null}),null).done).toBe(true);
  expect(nextStep(match({camera_profile_id:null}),analysis([])).done).toBe(true);
 });
});
