import {isUuid} from './query';
export type PublicContext={calendarReturn?:string;tournamentReturn?:string;teamReturn?:string;matchReturn?:string};
type Kind='calendar'|'tournament'|'team'|'match';
const keys:Record<Kind,keyof PublicContext>={calendar:'calendarReturn',tournament:'tournamentReturn',team:'teamReturn',match:'matchReturn'};
function safe(value:unknown,kind:Kind):string|undefined{
 if(typeof value!=='string'||value.length>3000||!value.startsWith('/')||value.startsWith('//'))return;
 try{const u=new URL(value,'https://local.invalid');if(u.origin!=='https://local.invalid')return;const p=u.pathname.split('/').filter(Boolean);
  const valid=kind==='calendar'?u.pathname==='/'||u.pathname==='/watch':kind==='tournament'?p.length===3&&p[0]==='watch'&&p[1]==='tournaments'&&isUuid(p[2]):kind==='team'?p.length===5&&p[0]==='watch'&&p[1]==='tournaments'&&isUuid(p[2])&&p[3]==='teams'&&isUuid(p[4]):p.length===3&&p[0]==='watch'&&p[1]==='matches'&&isUuid(p[2]);
  return valid?u.pathname+u.search:undefined;
 }catch{return}
}
export function publicContext(value:unknown):PublicContext{const out:PublicContext={};if(!value||typeof value!=='object')return out;for(const kind of Object.keys(keys) as Kind[]){const key=keys[kind],href=safe((value as PublicContext)[key],kind);if(href)out[key]=href}return out}
export function publicForward(value:unknown,kind:Kind,href:string):PublicContext{
 const out=publicContext(value);if(kind==='calendar'){delete out.tournamentReturn;delete out.teamReturn;delete out.matchReturn}else if(kind==='tournament'){delete out.teamReturn;delete out.matchReturn}else if(kind==='team')delete out.matchReturn;
 const target=safe(href,kind);if(target)out[keys[kind]]=target;return out;
}
export function publicBack(value:unknown,current:string,kinds:Kind[],fallback:{href:string;label:string}){
 const state=publicContext(value);const labels:Record<Kind,string>={calendar:'← К календарю матчей',tournament:'← К турниру',team:'← К команде',match:'← К матчу'};
 for(const kind of kinds){const href=state[keys[kind]];if(href&&href!==current){const returned={...state};const levels=Object.keys(keys) as Kind[];for(const level of levels.slice(levels.indexOf(kind)))delete returned[keys[level]];return {href,label:labels[kind],state:returned}}}
 return {...fallback,state};
}
