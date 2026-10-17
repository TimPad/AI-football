import {test,expect} from 'vitest';
import {protocolPublicationState} from './readiness';
test('a reopened draft alone does not pretend that a new confirmed version exists',()=>{
 expect(protocolPublicationState({published_version_id:'v1',latest_confirmed_version_id:'v1'})).toBe('published');
 expect(protocolPublicationState({published_version_id:'v1',latest_confirmed_version_id:'v2'})).toBe('new_version');
 expect(protocolPublicationState({published_version_id:null,latest_confirmed_version_id:'v1'})).toBe('ready');
 expect(protocolPublicationState({published_version_id:null,latest_confirmed_version_id:null})).toBe('draft');
});
