import {it,expect} from 'vitest';import {zonedToUtc,localInput} from './timezone';
it('saves Moscow local time independently of browser timezone',()=>{expect(zonedToUtc('2026-10-13T19:00','Europe/Moscow')).toBe('2026-10-13T16:00:00.000Z');expect(localInput('2026-10-13T16:00:00Z','Europe/Moscow')).toBe('2026-10-13T19:00')});
it('rejects non-existent DST times',()=>{expect(()=>zonedToUtc('2026-03-29T02:30','Europe/Berlin')).toThrow()});
