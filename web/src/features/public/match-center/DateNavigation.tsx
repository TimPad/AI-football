import {ChevronLeft,ChevronRight,CalendarDays} from 'lucide-react';
import {localDay,shiftDay} from '../../matches/timezone';
export const ZONE='Europe/Moscow';
export const today=()=>localDay(new Date().toISOString(),ZONE);
export function DateNavigation({day,onDayChange}:{day:string,onDayChange:(d:string)=>void}){
 const label=new Intl.DateTimeFormat('ru-RU',{month:'long',year:'numeric'}).format(new Date(day+'T12:00:00Z'));
 return <div className="center-dates"><div className="center-date-head"><h2>{label}</h2><button onClick={()=>onDayChange(today())}>Сегодня</button><label className="center-date-picker"><CalendarDays/><span className="sr-only">Выбрать дату</span><input type="date" aria-label="Дата матчей" value={day} onChange={e=>{if(e.target.value)onDayChange(e.target.value)}}/></label></div>
  <div className="center-date-strip"><button className="icon-button" aria-label="Предыдущий день" onClick={()=>onDayChange(shiftDay(day,-1))}><ChevronLeft/></button><div className="center-date-days">{Array.from({length:7},(_,i)=>shiftDay(day,i-3)).map(d=><button key={d} aria-pressed={day===d} onClick={()=>onDayChange(d)}><span>{new Intl.DateTimeFormat('ru-RU',{weekday:'short'}).format(new Date(d+'T12:00:00Z'))}</span><b>{Number(d.slice(-2))}</b></button>)}</div><button className="icon-button" aria-label="Следующий день" onClick={()=>onDayChange(shiftDay(day,1))}><ChevronRight/></button></div>
 </div>;
}
