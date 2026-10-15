import {afterEach,describe,expect,it,vi} from 'vitest';
import type {PublicMatch} from '../../api/domain';
import {loadPublicSection,SECTION_SOURCES} from './matchLoader';

const match={id:'m1',public_protocol_id:'pp1',tournament:{id:'t1'}} as unknown as PublicMatch;
function stub(responses:Record<string,{status:number,body?:unknown}>){
 const paths:string[]=[];
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{
  const path=String(input);paths.push(path);
  const hit=Object.entries(responses).find(([k])=>path.includes(k));
  const value=hit?.[1]??{status:404,body:{error:{code:'not_found',message:'Нет'}}};
  return new Response(JSON.stringify(value.body??{}),{status:value.status});
 }));
 return paths;
}
afterEach(()=>vi.unstubAllGlobals());

describe('public section loader',()=>{
 it('loads only public dependencies of the selected section',async()=>{
  const paths=stub({'/public/protocols/pp1':{status:200,body:{number:2}}});
  const model=await loadPublicSection(match,'events',null,new AbortController().signal);
  expect(paths).toEqual(['/api/v1/public/protocols/pp1']);
  expect(model.protocol).toEqual({status:'ready',value:{number:2}});
  expect(model.cv).toBeUndefined();
 });
 it('does not ask private routes when the protocol pointer is absent',async()=>{
  const paths=stub({});
  const model=await loadPublicSection({...match,public_protocol_id:null},'events',null,new AbortController().signal);
  expect(paths).toEqual([]);
  expect(model.protocol).toEqual({status:'absent'});
 });
 it('keeps sources independent: 404 is absent, 500 is a block error',async()=>{
  const paths=stub({'/public/protocols/pp1':{status:200,body:{number:2}},
   '/public/matches/m1/analysis':{status:500,body:{error:{code:'x',message:'Сбой'}}},
   '/public/matches/m1/ratings':{status:200,body:{snapshot_id:'A',items:[]}}});
  const model=await loadPublicSection(match,'overview',null,new AbortController().signal);
  expect(model.protocol?.status).toBe('ready');
  expect(model.cv).toEqual({status:'error',message:'Сбой'});
  expect(model.ratings?.status).toBe('ready');
  expect(paths.every(p=>p.startsWith('/api/v1/public/'))).toBe(true);
  stub({'/public/matches/m1/ratings':{status:200,body:{snapshot_id:null,items:[]}}});
  const empty=await loadPublicSection(match,'stats',null,new AbortController().signal);
  expect(empty.cv).toEqual({status:'absent'});
  expect(empty.ratings).toEqual({status:'absent'});
 });
 it('passes the selected edition and never loads understanding or evidence',async()=>{
  const paths=stub({'/public/matches/m1/ratings':{status:200,body:{snapshot_id:'A',items:[]}}});
  await loadPublicSection(match,'players','edition-A',new AbortController().signal);
  expect(paths).toContain('/api/v1/public/matches/m1/ratings?snapshot_id=edition-A');
  expect(paths.some(p=>/understanding|evidence|\/players\//.test(p))).toBe(false);
  expect(SECTION_SOURCES.video).toEqual([]);
 });
 it('rejects when the context is aborted',async()=>{
  stub({});const controller=new AbortController();controller.abort();
  await expect(loadPublicSection(match,'overview',null,controller.signal)).rejects.toThrow();
 });
});
