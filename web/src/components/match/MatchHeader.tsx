import './match.css';
import {useState,type ReactNode} from 'react';
import {Link,useLocation} from 'react-router-dom';
import type {PublicMatch} from '../../api/domain';
import {statuses} from '../../api/domain';
import {CircleDot} from 'lucide-react';
import {publicForward} from '../../features/navigation/publicContext';
import {dateTime} from '../../features/matches/timezone';

// Только публичный логотип; при ошибке или отсутствии — инициал, а не приватный URL.
export function TeamCrest({name,logoId,side,size='md'}:{name:string;logoId?:string|null;side:'home'|'away';size?:'sm'|'md'}){
 const [failed,setFailed]=useState(false);
 return <span className={`crest crest-${side} crest-${size}`} aria-hidden="true">{logoId&&!failed
  ?<img src={`/api/v1/public/catalog/team-logos/${logoId}`} alt="" onError={()=>setFailed(true)}/>
  :name.trim().charAt(0).toUpperCase()||'?'}</span>;
}

export type HeaderScorer={key:string;name:string;minute:string;note:string|null};

export function MatchHeader({match:m,resultNote,tournamentHref,scorers,children}:{match:PublicMatch;resultNote?:string|null;
 tournamentHref?:string;scorers?:{home:HeaderScorer[];away:HeaderScorer[]}|null;children?:ReactNode}){
 const location=useLocation();const forward=publicForward(location.state,'match',location.pathname+location.search);
 const score=m.score.home==null||m.score.away==null?null:`${m.score.home} : ${m.score.away}`;
 return <header className="match-header">
  <nav className="match-crumbs" aria-label="Путь"><Link state={forward} to={tournamentHref??`/watch/tournaments/${m.tournament.id}`}>{m.tournament.name}</Link><span aria-hidden="true">/</span><span>Матчи</span></nav>
  <div className="match-scoreline">
   <span className="match-team home"><TeamCrest name={m.home_name} logoId={m.home_logo_id} side="home"/><Link to={`/watch/tournaments/${m.tournament.id}/teams/${m.home_team_id}`} state={forward}><b>{m.home_name}</b></Link></span>
   <span className="match-score" aria-label={score?`Счёт ${score}`:'Результат не опубликован'}>{score??'— : —'}</span>
   <span className="match-team away"><Link to={`/watch/tournaments/${m.tournament.id}/teams/${m.away_team_id}`} state={forward}><b>{m.away_name}</b></Link><TeamCrest name={m.away_name} logoId={m.away_logo_id} side="away"/></span>
  </div>
  <p className="match-meta"><span className={`match-status ${m.status}`}>{statuses[m.status]}</span>{resultNote&&<span className="match-note">{resultNote}</span>}</p>
  <p className="match-meta muted">{dateTime(m.scheduled_at,m.tournament.timezone)} · {m.hall?.name||m.venue_label||'Площадка не указана'}</p>
  {scorers&&(scorers.home.length>0||scorers.away.length>0)&&<div className="match-scorers" aria-label="Авторы голов">
   <ul className="home">{scorers.home.map(s=><li key={s.key}>{s.name}{s.note&&<small> ({s.note})</small>} <span className="num">{s.minute}</span></li>)}</ul>
   <CircleDot aria-hidden="true"/>
   <ul className="away">{scorers.away.map(s=><li key={s.key}>{s.name}{s.note&&<small> ({s.note})</small>} <span className="num">{s.minute}</span></li>)}</ul>
  </div>}
  {children}
 </header>;
}
