import {Link,useLocation} from 'react-router-dom';
import {ChevronDown,Radio} from 'lucide-react';
import type {PublicMatch,PublicTournament} from '../../../api/domain';
import {statuses} from '../../../api/domain';
import {TeamCrest} from '../../../components/match/MatchHeader';
import {Score} from '../Schedule';
import {matchTime} from '../../matches/timezone';
import {ZONE} from './DateNavigation';
export function TournamentMatchGroup({tournament:t,total,items,closed,onToggle,onOpen}:{tournament:PublicTournament,total:number,items:PublicMatch[],closed:boolean,onToggle:()=>void,onOpen:()=>void}){
 const location=useLocation();
 return <section className="center-group"><div className="center-group-head"><button aria-expanded={!closed} aria-label={`${closed?'Развернуть':'Свернуть'} ${t.name}`} onClick={onToggle}><ChevronDown className={closed?'closed':''}/></button><div><Link aria-label={`Открыть турнир ${t.name}`} to={`/watch/tournaments/${t.id}`}>{t.name}</Link><small>Сезон {t.season} · Матчей: {total}</small></div></div>
  {!closed&&items.map(m=><article key={m.id} className={`center-match ${m.status}`}><div className="center-match-time"><b>{matchTime(m.scheduled_at,ZONE)}</b><small>{statuses[m.status]}</small></div>
   <div className="center-match-teams"><div><TeamCrest name={m.home_name} logoId={m.home_logo_id} side="home" size="sm"/><b>{m.home_name}</b></div><div><TeamCrest name={m.away_name} logoId={m.away_logo_id} side="away" size="sm"/><b>{m.away_name}</b></div></div>
   <div className="center-match-score"><Score match={m}/>{m.status==='live'&&<small>Опубликованный счёт</small>}</div><div className="center-match-meta"><span>{m.hall?.name||m.venue_label}</span>{(m.broadcast_url||m.broadcast_embed_url)&&<Radio aria-label="Есть видео"/>}</div>
   <Link className="center-open" aria-label={`Открыть матч ${m.home_name} — ${m.away_name}`} state={{calendarReturn:location.pathname+location.search}} onClick={onOpen} to={`/watch/matches/${m.id}`}>Открыть →</Link>
  </article>)}
 </section>;
}
