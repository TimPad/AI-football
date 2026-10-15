import {TournamentRatings} from '../ratings/TournamentRatings';
import {Link,useParams} from 'react-router-dom';
import {Trophy,ArrowUpRight} from 'lucide-react';
import {all,api} from '../../api/client';
import type {PublicTournament,PublicMatch} from '../../api/domain';
import {useLoad,Loading,ErrorBox,Empty} from '../../components/ui';
import {Schedule} from './Schedule';

export function PublicHome(){const state=useLoad(()=>all<PublicTournament>('/public/tournaments'),'public-tournaments');return <><div className="spectator-intro"><Trophy/><h1>Футбол, который нас объединяет</h1><p>Выберите турнир, чтобы посмотреть расписание, результаты и трансляции матчей.</p></div>{!state.data?<Loading error={state.error} retry={state.reload}/>:<><ErrorBox error={state.error}/>{state.data.length?<div className="public-tournaments">{state.data.map(t=><Link className="public-tournament" key={t.id} to={`/watch/tournaments/${t.id}`}><span className="muted">Сезон {t.season}</span><h2>{t.name}</h2><p>{t.starts_on} — {t.ends_on}</p><span>Матчи и расписание<ArrowUpRight/></span></Link>)}</div>:<Empty>Турниров пока нет. Расписание появится здесь, когда организатор добавит матчи.</Empty>}</>}</>}
export function PublicTournamentPage(){const {id}=useParams();return <TournamentContent key={id} id={id!}/>}
function TournamentContent({id}:{id:string}){const state=useLoad(async()=>{const [tournament,matches]=await Promise.all([api<PublicTournament>(`/public/tournaments/${id}`),all<PublicMatch>(`/public/tournaments/${id}/matches`)]);return {tournament,matches}},id);if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const {tournament:t,matches}=state.data;return <><Link className="breadcrumb" to="/">Все турниры</Link><div className="page-head"><div><p className="muted">Сезон {t.season}</p><h1>{t.name}</h1></div><button onClick={state.reload}>Обновить расписание</button></div><ErrorBox error={state.error}/><Schedule matches={matches} timezone={t.timezone}/><TournamentRatings tournamentId={id} publicView/></>}
