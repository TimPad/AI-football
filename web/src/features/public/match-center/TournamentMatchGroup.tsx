import {publicForward} from '../../navigation/publicContext';
import {Link,useLocation} from 'react-router-dom';
import {ChevronDown} from 'lucide-react';
import type {PublicMatch,PublicTournament} from '../../../api/domain';
import {MatchRow} from './MatchRow';
export function TournamentMatchGroup({tournament:t,total,items,closed,onToggle,onOpen}:{tournament:PublicTournament,total:number,items:PublicMatch[],closed:boolean,onToggle:()=>void,onOpen:()=>void}){
 const location=useLocation();const forward=publicForward(location.state,'calendar',location.pathname+location.search);
 return <section className="center-group"><div className="center-group-head"><button aria-expanded={!closed} aria-label={`${closed?'Развернуть':'Свернуть'} ${t.name}`} onClick={onToggle}><ChevronDown className={closed?'closed':''}/></button><div><Link aria-label={`Открыть турнир ${t.name}`} state={forward} onClick={onOpen} to={`/watch/tournaments/${t.id}`}>{t.name}</Link><small>Сезон {t.season} · Матчей: {total}</small></div></div>
  {!closed&&items.map(m=><MatchRow key={m.id} match={m} onOpen={onOpen}/>)}
 </section>;
}
