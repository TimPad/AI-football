import {Link} from 'react-router-dom';
import {api} from '../../api/client';
import type {PublicMatch} from '../../api/domain';
import {statuses} from '../../api/domain';
import {useLoad} from '../../components/ui';
import {YandexMapsLink} from '../../components/YandexMapsLink';
import {dateTime} from '../matches/timezone';

// Календарная дата матча в часовом поясе турнира — для списка «Матчи дня».
const localDay=(iso:string,tz:string)=>new Intl.DateTimeFormat('en-CA',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(iso));

// Боковая колонка гостевого матча: место и соседние матчи турнира; трансляция — в обзоре и «Видео».
export function MatchAside({match:m}:{match:PublicMatch}){
 const tz=m.tournament.timezone;const day=localDay(m.scheduled_at,tz);
 const others=useLoad(()=>api<{items:PublicMatch[];total:number}>(`/public/tournaments/${m.tournament.id}/matches?day=${day}&limit=20`),`${m.tournament.id}:${day}`);
 const rest=(others.data?.items??[]).filter(x=>x.id!==m.id);
 return <div className="match-aside">
  <section className="aside-card"><h3>Матч</h3><p className="num">{dateTime(m.scheduled_at,tz)}</p>
   <p>{m.hall?.name||m.venue_label||'Площадка не указана'}</p>
   {m.hall&&<><p className="muted small">{m.hall.address}{m.hall.pitch_length_m&&m.hall.pitch_width_m?` · поле ${m.hall.pitch_length_m} × ${m.hall.pitch_width_m} м`:''}</p><YandexMapsLink address={m.hall.address}/></>}
  </section>
  {rest.length>0&&<section className="aside-card"><h3>Матчи дня · {m.tournament.name}</h3><ul className="day-matches">{rest.map(x=>
   <li key={x.id}><Link to={`/watch/matches/${x.id}`}><span>{x.home_name}</span><b className="num">{x.score.home==null||x.score.away==null?dateTime(x.scheduled_at,tz).split(', ').pop():`${x.score.home} : ${x.score.away}`}</b><span>{x.away_name}</span></Link>
    <small className="muted">{statuses[x.status]}</small></li>)}</ul></section>}
 </div>;
}
