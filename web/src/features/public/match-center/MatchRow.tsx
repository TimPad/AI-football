import {publicForward} from '../../navigation/publicContext';
import {Link,useLocation} from 'react-router-dom';
import {Radio} from 'lucide-react';
import type {PublicMatch} from '../../../api/domain';
import {statuses} from '../../../api/domain';
import {TeamCrest} from '../../../components/match/MatchHeader';
import {Score} from '../Schedule';
import {matchTime} from '../../matches/timezone';
import {ZONE} from './DateNavigation';
const shortDate=(utc:string)=>new Intl.DateTimeFormat('ru-RU',{timeZone:ZONE,day:'numeric',month:'short'}).format(new Date(utc));
// The whole row is one target that opens the match; teams are reached from the match page.
export function MatchRow({match:m,withDate=false,withTournament=false,onOpen}:{match:PublicMatch,withDate?:boolean,withTournament?:boolean,onOpen?:()=>void}){
 const location=useLocation();const forward=publicForward(location.state,'calendar',location.pathname+location.search);
 const known=m.score.home!=null&&m.score.away!=null;const status=m.status==='scheduled'?null:statuses[m.status];
 const place=m.hall?.name||m.venue_label;const video=!!(m.broadcast_url||m.broadcast_embed_url);
 return <Link className={`center-match ${m.status}`} aria-label={`Открыть матч ${m.home_name} — ${m.away_name}${known?`, ${m.score.home} : ${m.score.away}`:''}`} state={forward} onClick={onOpen} to={`/watch/matches/${m.id}`}>
  <span className="center-match-time">{withDate?<><b>{shortDate(m.scheduled_at)}</b><small>{matchTime(m.scheduled_at,ZONE)}</small></>:<b>{matchTime(m.scheduled_at,ZONE)}</b>}{status&&<small className="center-match-status">{status}</small>}</span>
  <span className="center-match-teams"><span><TeamCrest name={m.home_name} logoId={m.home_logo_id} side="home" size="sm"/><b>{m.home_name}</b></span><span><TeamCrest name={m.away_name} logoId={m.away_logo_id} side="away" size="sm"/><b>{m.away_name}</b></span></span>
  <span className="center-match-score"><Score match={m}/>{m.status==='live'&&<small>Опубликованный счёт</small>}</span>
  {(withTournament||place||video)&&<span className="center-match-meta">{withTournament&&<span>{m.tournament.name}</span>}{place&&<span>{place}</span>}{video&&<Radio aria-label="Есть видео"/>}</span>}
 </Link>;
}
