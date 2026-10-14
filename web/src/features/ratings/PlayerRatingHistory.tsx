import {useState} from 'react';
import {api,all} from '../../api/client';
import type {Tournament} from '../../api/domain';
import {useLoad,Loading,Field} from '../../components/ui';
import type {PlayerRatings} from './types';
import {MatchRating} from './MatchRating';
import {RankingTable} from './TournamentRatings';
export function PlayerRatingHistory({playerId,initialTournament='',publicView=false}:{playerId:string,initialTournament?:string,publicView?:boolean}){
 const tournaments=useLoad(()=>all<Tournament>(`${publicView?'/public':''}/tournaments`),`${playerId}:${publicView}`);const [tid,setTid]=useState(initialTournament);
 return <section className="surface"><h2>Оценки и история турнира</h2><p className="muted">Издания с разными базами времени и reference не объединяются в одну динамику.</p><Field label="Турнир истории рейтинга"><select value={tid} onChange={e=>setTid(e.target.value)}><option value="">Выберите турнир</option>{tournaments.data?.map(t=><option key={t.id} value={t.id}>{t.name} · {t.season}</option>)}</select></Field>{tid&&<History key={`${tid}:${playerId}`} tid={tid} playerId={playerId} publicView={publicView}/>}</section>
}
function History({tid,playerId,publicView}:{tid:string,playerId:string,publicView:boolean}){
 const state=useLoad(()=>api<PlayerRatings>(`${publicView?'/public':''}/players/${playerId}/ratings?tournament_id=${tid}`),`${tid}:${playerId}`);
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const d=state.data;
 const byEdition=new Map<string,typeof d.matches>();for(const m of d.matches){const key=`${m.model_version} · ${m.reference_version.slice(0,8)} · ${m.profile_id} · ${m.time_basis} · ${m.role}`;byEdition.set(key,[...(byEdition.get(key)??[]),m])}
 return <>{!d.snapshot_id?<p>Рейтинг в этом турнире пока не доступен.</p>:<><RankingTable rows={d.summary} publicView={publicView} tournamentId={tid}/>{[...byEdition].map(([key,rows])=><div key={key}><h3>Динамика: {key}</h3><svg className="rating-trend" viewBox="0 0 600 125" role="img" aria-label="Матчевые оценки: пропуски не соединяются и не заменяются нулём"><path d="M20 10V105H580" fill="none" stroke="#cbd5e1"/>{rows.map((m,i)=>{if(m.score===null)return null;const x=rows.length===1?300:30+i*540/(rows.length-1),y=105-m.score*.9;return <g key={`${m.match_id}:${m.role}`}><circle cx={x} cy={y} r="5" fill="#147562"/><text x={x} y={y-10} textAnchor="middle" fontSize="12">{m.display_rating?.toFixed(1)}</text></g>})}</svg><div className="rating-cards">{rows.map(m=><div key={`${m.match_id}:${m.role}`}><p>{new Date(m.scheduled_at).toLocaleString('ru-RU')} · {m.team_name}</p><MatchRating value={m} publicView={publicView}/></div>)}</div></div>)}</>}</>;
}
