export function localInput(utc:string,zone:string){const parts=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(utc));const get=(k:string)=>parts.find(p=>p.type===k)!.value;return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`}
export function zonedToUtc(value:string,zone:string){
 const target=Date.parse(value+'Z');if(!Number.isFinite(target))throw new Error('Укажите дату и время');
 let guess=target;for(let i=0;i<3;i++){const shown=Date.parse(localInput(new Date(guess).toISOString(),zone)+'Z');guess+=target-shown}
 if(localInput(new Date(guess).toISOString(),zone)!==value)throw new Error('Такого местного времени нет при переходе часов. Выберите другое время.');
 for(const delta of [-3600000,3600000])if(localInput(new Date(guess+delta).toISOString(),zone)===value)throw new Error('Это время повторяется при переходе часов. Выберите другое время.');
 return new Date(guess).toISOString();
}
export const dateTime=(utc:string,zone:string)=>new Intl.DateTimeFormat('ru-RU',{timeZone:zone,dateStyle:'medium',timeStyle:'short'}).format(new Date(utc));
export function localDay(value:string,timezone:string){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(value));
 return ['year','month','day'].map(key=>parts.find(p=>p.type===key)!.value).join('-');
}
export const matchTime=(value:string,timezone:string)=>new Intl.DateTimeFormat('ru-RU',{timeZone:timezone,hour:'2-digit',minute:'2-digit'}).format(new Date(value));
// Минуты от полуночи местного дня турнира.
export function localMinutes(value:string,timezone:string){const [h,m]=localInput(value,timezone).slice(11).split(':').map(Number);return h*60+m}
export function shiftDay(day:string,delta:number){const d=new Date(`${day}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+delta);return d.toISOString().slice(0,10)}
