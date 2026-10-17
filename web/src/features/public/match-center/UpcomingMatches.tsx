import {useState} from 'react';
import {Link} from 'react-router-dom';
import type {components} from '../../../api/types';
import {ErrorBox,Loading} from '../../../components/ui';
import {dateTime,localDay} from '../../matches/timezone';
import {usePublicRequest,useWideScreen} from './request';
import {ZONE} from './DateNavigation';
export function UpcomingMatches({query,onShowDay,tick}:{query:string,onShowDay:(d:string)=>void,tick:number}){
 const wide=useWideScreen();
 const [retry,setRetry]=useState(0);const state=usePublicRequest<components['schemas']['PublicUpcomingMatches']>(`/public/matches/upcoming?${query}`,tick+retry);
 if(state.data&&!state.data.items.length)return null;
 return <details open={wide} className="center-upcoming center-side-panel"><summary>Ближайшие матчи</summary><p className="muted small">От текущего времени · Время московское</p>{!state.data?<Loading error={state.error} retry={()=>setRetry(n=>n+1)}/>:<><ErrorBox error={state.error}/>{state.data.items.map(m=><article key={m.id}><small>{m.tournament.name} · {dateTime(m.scheduled_at,ZONE)}</small><Link to={`/watch/matches/${m.id}`}><b>{m.home_name} — {m.away_name}</b></Link><button className="quiet" onClick={()=>onShowDay(localDay(m.scheduled_at,ZONE))}>Показать этот день</button></article>)}</>}</details>;
}
