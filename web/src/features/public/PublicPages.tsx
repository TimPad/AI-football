import {PublicMatchCenter} from './match-center/PublicMatchCenter';
import {useDocumentTitle} from '../../components/useDocumentTitle';
export function PublicHome(){return <PublicMatchCenter/>}
import {TournamentRatings} from '../ratings/TournamentRatings';
import {Link,useParams,useLocation} from 'react-router-dom';
import {useQueryPatch} from '../navigation/useQueryPatch';
import {SectionNavigation} from '../../components/match/SectionNavigation';
import {isUuid,patchQuery} from '../navigation/query';
import {Trophy,ArrowUpRight} from 'lucide-react';
import {all,api} from '../../api/client';
import type {PublicTournament,PublicMatch} from '../../api/domain';
import {useLoad,Loading,ErrorBox,Empty} from '../../components/ui';
import {publicBack,publicForward} from '../navigation/publicContext';
import {PublicTournamentTeams} from './PublicTeamPage';
import {Schedule} from './Schedule';
import {dateRange} from '../matches/timezone';

export function PublicTournamentCatalog(){useDocumentTitle('Турниры');const state=useLoad(()=>all<PublicTournament>('/public/tournaments'),'public-tournaments');return <><div className="spectator-intro"><Trophy/><h1>Футбол, который нас объединяет</h1><p>Выберите турнир, чтобы посмотреть расписание, результаты и трансляции матчей.</p></div>{!state.data?<Loading error={state.error} retry={state.reload}/>:<><ErrorBox error={state.error}/>{state.data.length?<div className="public-tournaments">{state.data.map(t=><Link className="public-tournament" key={t.id} to={`/watch/tournaments/${t.id}`}><span className="muted">Сезон {t.season}</span><h2>{t.name}</h2><p>{dateRange(t.starts_on,t.ends_on)}</p><span>Матчи и расписание<ArrowUpRight/></span></Link>)}</div>:<Empty>Турниров пока нет. Расписание появится здесь, когда организатор добавит матчи.</Empty>}</>}</>}
export function PublicTournamentPage(){const {id}=useParams();return <TournamentContent key={id} id={id!}/>}
function TournamentContent({id}:{id:string}){
 const location=useLocation();const href=location.pathname+location.search;const forward=publicForward(location.state,'tournament',href);const back=publicBack(location.state,href,['calendar'],{href:'/watch/tournaments',label:'← Все турниры'});
 const [params,update]=useQueryPatch();const tab=['ratings','teams'].includes(params.get('tab')??'')?params.get('tab')!:'matches';
 const snapshot=isUuid(params.get('snapshot_id'))?params.get('snapshot_id')!:'';
 const state=useLoad(async()=>{const [tournament,matches]=await Promise.all([api<PublicTournament>(`/public/tournaments/${id}`),all<PublicMatch>(`/public/tournaments/${id}/matches`)]);return {tournament,matches}},id);
 useDocumentTitle(state.data?.tournament.name);
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const {tournament:t,matches}=state.data;
 return <><Link className="breadcrumb" to={back.href} state={back.state}>{back.label}</Link><div className="page-head"><div><p className="muted">Сезон {t.season} · {dateRange(t.starts_on,t.ends_on)}</p><h1>{t.name}</h1></div></div>
  <SectionNavigation label="Разделы турнира" items={[{id:'matches',label:'Матчи'},{id:'teams',label:'Команды'},{id:'ratings',label:'Рейтинги'}]} selected={tab}
   onSelect={value=>update({tab:value==='matches'?null:value})} href={value=>`?${patchQuery(params,{tab:value==='matches'?null:value})}`}/>
  <ErrorBox error={state.error}/>
  <div className="tournament-section">{tab==='matches'?<Schedule wholeRow matches={matches} timezone={t.timezone} matchState={forward} teamHref={team=>`/watch/tournaments/${id}/teams/${team}`} teamState={forward}/>:tab==='teams'?<PublicTournamentTeams tournamentId={id}/>:<TournamentRatings tournamentId={id} publicView initialSnapshot={snapshot}/>}</div></>;
}
