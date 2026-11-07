import {describe,expect,it} from 'vitest';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {contrast} from '../features/stages/contrast';

const css=readFileSync(resolve(__dirname,'tokens.css'),'utf8');
const read=(block:string)=>Object.fromEntries([...block.matchAll(/(--[\w-]+):(#[0-9a-fA-F]{3,6})\b/g)].map(m=>[m[1],m[2]]));
const light=read(css.slice(css.indexOf(':root{'),css.indexOf('}')));
const dark={...light,...read(css.slice(css.indexOf('@media (prefers-color-scheme:dark)')))};
const TEXT=[['--text','--app-bg'],['--text','--surface'],['--text','--surface-2'],['--text','--hover'],['--text-muted','--surface'],['--text-muted','--app-bg'],['--text-muted','--surface-2'],
 ['--link','--surface'],['--accent-ink','--accent'],['--accent-soft-ink','--accent-soft'],['--accent-soft-ink','--surface'],['--warn','--warn-soft'],['--warn','--surface'],['--danger','--danger-soft'],['--danger','--surface'],
 ['--ok','--ok-soft'],['--ok','--surface'],['--live','--surface'],['--on-danger','--danger'],['--selected-ink','--selected-bg'],['--text','--info-soft']];
const UI=[['--line-strong','--surface'],['--accent-line','--surface'],['--focus','--surface'],['--accent-line','--app-bg']];

describe('контраст токенов (WCAG 2.2 AA)',()=>{
 for(const [name,theme] of [['светлая',light],['тёмная',dark]] as const){
  it(`${name}: текст не ниже 4,5:1`,()=>{for(const [fg,bg] of TEXT)expect(contrast(theme[fg],theme[bg]),`${fg} на ${bg}`).toBeGreaterThanOrEqual(4.5)});
  it(`${name}: линии и значки не ниже 3:1`,()=>{for(const [fg,bg] of UI)expect(contrast(theme[fg],theme[bg]),`${fg} на ${bg}`).toBeGreaterThanOrEqual(3)});
 }
});
