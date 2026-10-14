import {Link,useParams} from 'react-router-dom';
import {api} from '../../api/client';
import type {AnalysisHistory,Player} from '../../api/domain';
import {useLoad,Loading} from '../../components/ui';
import {AnalysisReport,measure} from './AnalysisReport';
export function PlayerHistory(){const {id}=useParams();const state=useLoad(async()=>{const [player,history]=await Promise.all([api<Player>(`/players/${id}`),api<AnalysisHistory>(`/players/${id}/analysis`)]);return {player,history}},id!);
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const {player,history}=state.data;
 return <><Link className="breadcrumb" to="/players">← Игроки</Link><div className="page-head"><div><h1>{player.name}</h1><p className="muted">История аналитики · {history.match_count} матчей с активным отчётом</p></div></div><section className="surface"><h2>Итоги по доступным записям</h2><p>Дистанция: {measure(history.totals.distance_m)} м · время в анализируемом видео: {measure(history.totals.observed_s)} с · темп: {measure(history.totals.m_per_min)} м/мин</p><p className="muted">Для каждого матча учитывается одна активная версия. Неполные показатели не заменяются нулём.</p></section>{!history.matches.length&&<p>Подтверждённой статистики пока нет.</p>}{history.matches.map(m=><div key={m.match_id}><h2><Link to={`/matches/${m.match_id}`}>{m.teams.home.name} — {m.teams.away.name}</Link></h2><p className="muted">{new Date(m.scheduled_at).toLocaleString('ru-RU')}</p><AnalysisReport players={[m]} partial={m.partial} linkPlayers={false}/></div>)}</>;
}
