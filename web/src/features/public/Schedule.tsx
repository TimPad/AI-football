import type {ReactNode} from 'react';
import {Link} from 'react-router-dom';
import {Radio,ChevronLeft,ChevronRight,ArrowRight} from 'lucide-react';
import type {PublicMatch} from '../../api/domain';
import {statuses} from '../../api/domain';
import {Empty} from '../../components/ui';
import {plural} from '../../components/plural';
import {TeamCrest} from '../../components/match/MatchHeader';
import {useQueryPatch} from '../navigation/useQueryPatch';
import {localDay,localMinutes,matchTime,shiftDay} from '../matches/timezone';
import './schedule.css';

export {localDay,matchTime};
export type ScheduleItem=Pick<PublicMatch,'id'|'scheduled_at'|'schedule_slot_s'|'venue_label'|'hall'|'home_name'|'away_name'|'status'|'score'|'broadcast_url'|'broadcast_embed_url'>
 &{home_logo_id?:string|null;away_logo_id?:string|null};
const PX_PER_MIN=1.6;
// Фильтр статуса нужен длинному расписанию; короткое читается целиком.
const STATUS_FILTER_FROM=11;

export function Score({match}:{match:Pick<ScheduleItem,'score'>}){
 const known=match.score.home!=null&&match.score.away!=null;
 return <span className="spectator-score" aria-label={known?`Счёт ${match.score.home} : ${match.score.away}`:'Результат не опубликован'}>{known?`${match.score.home} : ${match.score.away}`:'— : —'}</span>;
}
// Зал различается по UUID; для старых записей без зала — по подписи.
const venueKey=(m:ScheduleItem)=>m.hall?.id||m.venue_label||'Площадка не указана';
// В расписании — только название зала; адрес и карта — на странице матча.
const venueName=(m:ScheduleItem)=>m.hall?.name||m.venue_label||'Площадка не указана';
const endIso=(m:ScheduleItem)=>new Date(new Date(m.scheduled_at).getTime()+m.schedule_slot_s*1000).toISOString();
const hasVideo=(m:ScheduleItem)=>Boolean(m.broadcast_url||m.broadcast_embed_url);
export const timezoneLabel=(tz:string)=>tz==='Europe/Moscow'?'Время московское':`Время местное (${tz.split('/').pop()!.replace(/_/g,' ')})`;

function Teams({match:m}:{match:ScheduleItem}){
 return <div className="slot-teams"><span className="slot-team"><TeamCrest name={m.home_name} logoId={m.home_logo_id} side="home" size="sm"/><b>{m.home_name}</b></span>
  <Score match={m}/><span className="slot-team away"><b>{m.away_name}</b><TeamCrest name={m.away_name} logoId={m.away_logo_id} side="away" size="sm"/></span></div>;
}
function Open({match:m,href}:{match:ScheduleItem;href:string}){
 return <Link className="slot-open" to={href} aria-label={`Открыть матч ${m.home_name} — ${m.away_name}`}>Открыть матч<ArrowRight/></Link>;
}
const Status=({match:m}:{match:ScheduleItem})=><span className={`chip status-chip ${m.status}`}>{statuses[m.status]}</span>;

// Пересекающиеся матчи одного зала — соседние дорожки, без наложения.
function lanes(items:{start:number;end:number}[]){
 const ends:number[]=[];const lane=items.map(item=>{let i=ends.findIndex(e=>e<=item.start);if(i<0){i=ends.length;ends.push(item.end)}else ends[i]=item.end;return i});
 return {lane,count:Math.max(1,ends.length)};
}

// extra — отметка кабинета в строке матча (например, «На сайте»); у зрителя её нет.
export function Schedule({matches,timezone,matchHref=id=>`/watch/matches/${id}`,extra}:{matches:ScheduleItem[];timezone:string;matchHref?:(id:string)=>string;extra?:(id:string)=>ReactNode}){
 const [params,update]=useQueryPatch();
 const set=(patch:Record<string,string|null>)=>update(patch,{replace:true});
 const view=params.get('view')==='grid'?'grid':'list';
 const day=params.get('day')??'';const hall=params.get('hall_id')??'';const status=params.get('status')??'';
 const venues=[...new Set(matches.map(venueKey))];const names=new Map(matches.map(m=>[venueKey(m),venueName(m)]));
 const dates=[...new Set(matches.map(m=>localDay(m.scheduled_at,timezone)))].sort();
 const today=localDay(new Date().toISOString(),timezone);
 const shownDay=view==='grid'?day||dates.find(d=>d>=today)||dates[dates.length-1]||today:day;
 const shown=matches.filter(m=>(!shownDay||localDay(m.scheduled_at,timezone)===shownDay)&&(!hall||venueKey(m)===hall)&&(!status||m.status===status));
 const columns=venues.filter(v=>(!hall||hall===v)&&(view==='list'||shown.some(m=>venueKey(m)===v)));
 const baseDay=shownDay||today;
 // Элемент управления показывается, только когда он что-то меняет (или уже выбран в ссылке — чтобы его можно было сбросить).
 const show={day:dates.length>1||!!day,hall:venues.length>1||!!hall,status:matches.length>=STATUS_FILTER_FROM||!!status,view:venues.length>1||view==='grid'};
 const toolbar=show.day||show.hall||show.status||show.view;
 return <section className="schedule">
  {toolbar&&<div className="schedule-toolbar">
   {show.day&&<div className="day-stepper"><button className="icon-button" aria-label="Предыдущий день" onClick={()=>set({day:shiftDay(baseDay,-1)})}><ChevronLeft/></button>
    <input type="date" aria-label="Дата" value={shownDay} onChange={e=>set({day:e.target.value||null})}/>
    <button className="icon-button" aria-label="Следующий день" onClick={()=>set({day:shiftDay(baseDay,1)})}><ChevronRight/></button></div>}
   {show.hall&&<select aria-label="Фильтр по залу" value={hall} onChange={e=>set({hall_id:e.target.value||null})}><option value="">Все залы</option>{venues.map(v=><option key={v} value={v}>{names.get(v)}</option>)}</select>}
   {show.status&&<select aria-label="Фильтр по статусу" value={status} onChange={e=>set({status:e.target.value||null})}><option value="">Все статусы</option>{Object.entries(statuses).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select>}
   {(day||hall||status)&&<button onClick={()=>set({day:null,hall_id:null,status:null})}>Сбросить</button>}
   {show.view&&<div className="segmented view-switch" role="group" aria-label="Вид расписания">
    <button aria-pressed={view==='list'} onClick={()=>set({view:null})}>Список</button>
    <button aria-pressed={view==='grid'} onClick={()=>set({view:'grid'})}>Сетка</button></div>}
  </div>}
  {!shown.length?<Empty>{matches.length?'Матчей с такими условиями нет.':'Матчей пока нет.'}</Empty>
  :view==='list'?<div className="schedule-list">{shown.map(m=><article key={m.id} className="schedule-row">
    <div className="row-time num"><b>{matchTime(m.scheduled_at,timezone)}</b><small>{new Intl.DateTimeFormat('ru-RU',{timeZone:timezone,day:'numeric',month:'short'}).format(new Date(m.scheduled_at))}</small></div>
    <Teams match={m}/><span className="row-hall">{venueName(m)}</span>
    <div className="row-meta"><Status match={m}/>{extra?.(m.id)}<span className="row-video">{hasVideo(m)&&<><Radio aria-hidden="true"/>ВК</>}</span><Open match={m} href={matchHref(m.id)}/></div></article>)}</div>
  :<TimeGrid matches={shown} columns={columns} names={names} timezone={timezone} matchHref={matchHref}/>}
  <footer className="schedule-foot"><span>{plural(shown.length,['матч','матча','матчей'])}{columns.length>1?` · ${plural(columns.length,['зал','зала','залов'])}`:''}</span><span>{timezoneLabel(timezone)}</span></footer>
 </section>;
}

function TimeGrid({matches,columns,names,timezone,matchHref}:{matches:ScheduleItem[];columns:string[];names:Map<string,string>;timezone:string;matchHref:(id:string)=>string}){
 const spans=matches.map(m=>{const start=localMinutes(m.scheduled_at,timezone);return {m,start,end:start+m.schedule_slot_s/60}});
 const from=Math.floor(Math.min(...spans.map(s=>s.start))/30)*30,to=Math.ceil(Math.max(...spans.map(s=>s.end))/30)*30;
 const marks=Array.from({length:(to-from)/30+1},(_,i)=>from+i*30);
 const label=(min:number)=>`${String(Math.floor(min/60)%24).padStart(2,'0')}:${String(min%60).padStart(2,'0')}`;
 const height=(to-from)*PX_PER_MIN;
 return <div className="time-grid-scroll" tabIndex={0} aria-label="Прокрутка сетки">
  <div className="time-grid" role="table" aria-label="Сетка расписания" style={{gridTemplateColumns:`72px repeat(${columns.length},minmax(240px,1fr))`}}>
   <div role="rowgroup" className="time-grid-head"><div role="row"><span role="columnheader">Время</span>{columns.map(v=><span role="columnheader" key={v}>{names.get(v)}</span>)}</div></div>
   <div role="rowgroup" className="time-grid-body"><div role="row">
    <div role="cell" className="time-axis" style={{height}}>{marks.map(min=><span key={min} className={min%60?'half':''} style={{top:(min-from)*PX_PER_MIN}}>{label(min)}</span>)}</div>
    {columns.map(v=>{const own=spans.filter(s=>venueKey(s.m)===v).sort((a,b)=>a.start-b.start);const {lane,count}=lanes(own);
     return <div role="cell" key={v} className="time-column" style={{height}}>{marks.map(min=><i key={min} className="grid-line" style={{top:(min-from)*PX_PER_MIN}}/>)}
      {own.map((s,i)=><article key={s.m.id} className={`time-slot ${s.m.status}`} style={{top:(s.start-from)*PX_PER_MIN,height:(s.end-s.start)*PX_PER_MIN,
        left:`calc(${100*lane[i]/count}% + 4px)`,width:`calc(${100/count}% - 8px)`}}>
       <div className="slot-head"><span className="num">{matchTime(s.m.scheduled_at,timezone)} – {matchTime(endIso(s.m),timezone)}</span><Status match={s.m}/></div>
       <Teams match={s.m}/>
       <div className="slot-foot">{hasVideo(s.m)?<span className="row-video"><Radio aria-hidden="true"/>ВК</span>:<span/>}<Open match={s.m} href={matchHref(s.m.id)}/></div>
      </article>)}</div>;})}
   </div></div>
  </div>
 </div>;
}
