import {useState} from 'react';
import {Link} from 'react-router-dom';
import type {RatingPage} from '../../ratings/types';
import {Loading} from '../../../components/ui';
import {usePublicRequest} from './request';
import {ZONE} from './DateNavigation';
export function TournamentLeaders({tournamentId,tick=0}:{tournamentId:string,tick?:number}){
 const [retry,setRetry]=useState(0);const state=usePublicRequest<RatingPage>(`/public/tournaments/${tournamentId}/ratings?qualification=qualified&limit=5&offset=0`,tick+retry);
 if(!state.data)return <Loading error={state.error} retry={()=>setRetry(n=>n+1)}/>;const d=state.data;
 if(!d.snapshot_id)return <p className="muted">Рейтинг ещё не опубликован.</p>;
 return <><p className="muted small">Рейтинг всего турнира{d.published_at?` · опубликован ${new Date(d.published_at).toLocaleDateString('ru-RU',{timeZone:ZONE})}`:''}</p>
  {d.items.length?<ol className="center-leaders-list">{d.items.map(r=><li key={r.player_id}><span className="center-rank num">{r.rank??'—'}</span><div><Link to={`/watch/players/${r.player_id}?${new URLSearchParams({tournament_id:tournamentId,snapshot_id:d.snapshot_id!})}`}>{r.display_name}</Link><small>{r.teams?.map(t=>t.name).join(' · ')} · Матчей: {r.rated_match_count}</small></div><b className="center-rating num">{r.display_rating?.toFixed(1)??'—'}</b></li>)}</ol>:<p className="muted">Пока недостаточно данных для топа.</p>}
  <Link className="center-full-rating" to={`/watch/tournaments/${tournamentId}?${new URLSearchParams({tab:'ratings',snapshot_id:d.snapshot_id})}`}>Весь рейтинг</Link><p className="muted small">Пилотный рейтинг · Основной список</p>
 </>;
}
