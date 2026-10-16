import {Link} from 'react-router-dom';
import {statuses} from '../../api/domain';
import {Empty} from '../../components/ui';
import {dateTime} from '../matches/timezone';
import type {Data} from './TournamentPage';

// Только поля текущей сводки матчей; подробности версий — при открытии матча.
export function TournamentPublicationList({data:d,analytics}:{data:Data;analytics:boolean}){
 if(!d.matches.length)return <Empty>Матчей пока нет.</Empty>;
 return <section className="surface"><div className="panel-head"><div><h2>Готовность публикаций</h2>
  <p className="muted">Каждая публикация выполняется отдельно на странице матча. Рейтинг турнира публикуется в разделе «Рейтинги».</p></div></div>
  <div className="table-scroll"><table><thead><tr><th>Матч</th><th>Статус</th><th>Протокол на сайте</th><th>Видеоанализ на сайте</th><th/></tr></thead><tbody>
   {d.matches.map(m=><tr key={m.id}><td><b>{m.home.team.name} — {m.away.team.name}</b><small>{dateTime(m.scheduled_at,d.t.timezone)}</small></td>
    <td><span className={`chip status-chip ${m.status}`}>{statuses[m.status]}</span></td>
    <td>{m.published_version_id?<span className="chip ok">Опубликован</span>:<span className="chip">Не опубликован</span>}</td>
    <td>{m.published_analysis_run_id?<span className="chip ok">Видеоанализ опубликован</span>:<span className="chip">Видеоанализ не опубликован</span>}
     {analytics&&<small>Источники оценок — в публикации матча</small>}</td>
    <td><Link to={`/matches/${m.id}?tab=publication`} aria-label={`Публикация ${m.home.team.name} — ${m.away.team.name}`}>Открыть →</Link></td></tr>)}</tbody></table></div></section>;
}
