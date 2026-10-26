import {useState} from 'react';
import type {components} from '../../../api/types';
import {Loading} from '../../../components/ui';
import {usePublicRequest} from './request';
import {MatchRow} from './MatchRow';
type MatchList=components['schemas']['PublicUpcomingMatches'];
// A short list of other days' matches: recent results or the nearest games. Nothing is drawn when the list is empty.
export function MatchShortList({title,path,tick,className=''}:{title:string,path:string,tick:number,className?:string}){
 const [retry,setRetry]=useState(0);const state=usePublicRequest<MatchList>(path,tick+retry);
 if(state.data&&!state.data.items.length)return null;
 return <section className={`center-short-list ${className}`}><h2>{title}</h2>{!state.data?<Loading error={state.error} retry={()=>setRetry(n=>n+1)}/>:state.data.items.map(m=><MatchRow key={m.id} match={m} withDate withTournament/>)}</section>;
}
export function UpcomingMatches({query,tick}:{query:string,tick:number}){
 return <MatchShortList title="Ближайшие матчи" className="center-upcoming center-side-panel" path={`/public/matches/upcoming?${query}`} tick={tick}/>;
}
