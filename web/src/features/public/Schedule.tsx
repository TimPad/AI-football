import {useState} from 'react';
import {Link} from 'react-router-dom';
import {Radio,ArrowUpRight} from 'lucide-react';
import type {PublicMatch} from '../../api/domain';
import {statuses} from '../../api/domain';
import {Field,Empty} from '../../components/ui';

export function localDay(value:string,timezone:string){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(value));
 return ['year','month','day'].map(key=>parts.find(p=>p.type===key)!.value).join('-');
}
export const matchTime=(value:string,timezone:string)=>new Intl.DateTimeFormat('ru-RU',{timeZone:timezone,hour:'2-digit',minute:'2-digit'}).format(new Date(value));
export function Score({match}:{match:PublicMatch}){return <span className="spectator-score">{match.score.home??'—'} : {match.score.away??'—'}</span>}
function Slot({match,timezone}:{match:PublicMatch,timezone:string}){
 const end=new Date(new Date(match.scheduled_at).getTime()+match.schedule_slot_s*1000).toISOString();
 return <Link className={`schedule-slot ${match.status}`} to={`/watch/matches/${match.id}`}>
  <span className="slot-time">{matchTime(match.scheduled_at,timezone)} — {matchTime(end,timezone)}</span>
  <strong>{match.home_name} — {match.away_name}</strong><Score match={match}/>
  <span className="slot-foot">{statuses[match.status]}{(match.broadcast_url||match.broadcast_embed_url)&&<Radio aria-label="Трансляция ВК"/>}</span>
 </Link>;
}
const venueKey=(m:PublicMatch)=>m.hall?.id||m.venue_label||'Площадка не указана';
const venueName=(m:PublicMatch)=>m.hall?`${m.hall.name} · ${m.hall.address}`:m.venue_label||'Площадка не указана';
export function Schedule({matches,timezone}:{matches:PublicMatch[],timezone:string}){
 const [day,setDay]=useState('');const [venue,setVenue]=useState('');const [status,setStatus]=useState('');const [mode,setMode]=useState('list');
 const venues=[...new Set(matches.map(venueKey))];const names=new Map(matches.map(m=>[venueKey(m),venueName(m)]));
 const dates=[...new Set(matches.map(m=>localDay(m.scheduled_at,timezone)))];
 const today=localDay(new Date().toISOString(),timezone);
 const gridDay=day||dates.find(d=>d>=today)||dates[0]||today;
 const filtered=matches.filter(m=>(!day||localDay(m.scheduled_at,timezone)===day)&&(!venue||venueKey(m)===venue)&&(!status||m.status===status));
 const grid=filtered.filter(m=>localDay(m.scheduled_at,timezone)===gridDay);
 const columns=venues.filter(v=>!venue||venue===v);
 const times=[...new Set(grid.map(m=>m.scheduled_at))].sort();
 return <section className="spectator-schedule"><div className="schedule-toolbar"><div className="segmented" aria-label="Вид расписания"><button aria-pressed={mode==='list'} className={mode==='list'?'active':''} onClick={()=>setMode('list')}>Список матчей</button><button aria-pressed={mode==='grid'} className={mode==='grid'?'active':''} onClick={()=>setMode('grid')}>Сетка расписания</button></div><span className="muted">Время: {timezone}</span></div>
 <div className="filters"><Field label="Дата"><input type="date" value={mode==='grid'?gridDay:day} onChange={e=>setDay(e.target.value)}/></Field><Field label="Площадка"><select value={venue} onChange={e=>setVenue(e.target.value)}><option value="">Все площадки</option>{venues.map(v=><option key={v} value={v}>{names.get(v)}</option>)}</select></Field><Field label="Статус"><select value={status} onChange={e=>setStatus(e.target.value)}><option value="">Все матчи</option>{Object.entries(statuses).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></Field><button onClick={()=>{setDay('');setVenue('');setStatus('')}}>Сбросить</button></div>
 {mode==='list'?(!filtered.length?<Empty>На эту дату матчей нет.</Empty>:<div className="public-match-list">{filtered.map(m=><Link key={m.id} className="public-match-row" to={`/watch/matches/${m.id}`}><div className="match-date"><b>{matchTime(m.scheduled_at,timezone)}</b><small>{new Intl.DateTimeFormat('ru-RU',{timeZone:timezone,day:'numeric',month:'short'}).format(new Date(m.scheduled_at))}</small></div><div className="match-pair"><strong>{m.home_name} — {m.away_name}</strong><small>{venueName(m)}</small></div><Score match={m}/><span className={`status ${m.status}`}>{statuses[m.status]}</span><span className="match-broadcast">{(m.broadcast_url||m.broadcast_embed_url)?<><Radio/>ВК</>:<ArrowUpRight/>}</span></Link>)}</div>):(!grid.length?<Empty>На эту дату матчей нет.</Empty>:<><p className="muted">Интервалы включают время, отведённое на матч по регламенту.</p><div className="schedule-scroll" tabIndex={0} aria-label="Прокрутка сетки"><table className="schedule-grid" style={{minWidth:90+columns.length*230}} aria-label="Сетка расписания"><thead><tr><th>Начало</th>{columns.map(v=><th key={v}>{names.get(v)}</th>)}</tr></thead><tbody>{times.map(time=><tr key={time}><th scope="row">{matchTime(time,timezone)}</th>{columns.map(v=><td key={v}>{grid.filter(m=>m.scheduled_at===time&&venueKey(m)===v).map(m=><Slot key={m.id} match={m} timezone={timezone}/>)}</td>)}</tr>)}</tbody></table></div></>)}
 </section>;
}
