import {it,expect} from 'vitest';import {zonedToUtc,localInput} from './timezone';
it('saves Moscow local time independently of browser timezone',()=>{expect(zonedToUtc('2026-10-13T19:00','Europe/Moscow')).toBe('2026-10-13T16:00:00.000Z');expect(localInput('2026-10-13T16:00:00Z','Europe/Moscow')).toBe('2026-10-13T19:00')});
it('rejects non-existent DST times',()=>{expect(()=>zonedToUtc('2026-03-29T02:30','Europe/Berlin')).toThrow()});
import {localDay,localMinutes,shiftDay} from './timezone';
it('uses the tournament day and minutes, not the browser zone',()=>{expect(localDay('2026-10-19T22:30:00Z','Europe/Moscow')).toBe('2026-10-20');expect(localMinutes('2026-10-19T22:30:00Z','Europe/Moscow')).toBe(90);expect(shiftDay('2026-10-31',1)).toBe('2026-11-01');expect(shiftDay('2026-03-01',-1)).toBe('2026-02-28')});
