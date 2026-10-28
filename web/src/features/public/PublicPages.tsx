import {PublicMatchCenter} from './match-center/PublicMatchCenter';
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
import {StandingsView} from '../stages/StandingsView';
import {UnscheduledFixtures} from '../stages/UnscheduledFixtures';
import type {FixtureView,Standings} from '../stages/api';
import {Schedule} from './Schedule';
import {dateRange} from '../matches/timezone';

export function PublicTournamentCatalog(){const state=useLoad(()=>all<PublicTournament>('/public/tournaments'),'public-tournaments');return <><div className="spectator-intro"><Trophy/><h1>Футбол, который нас объединяет</h1><p>Выберите турнир, чтобы посмотреть расписание, результаты и трансляции матчей.</p></div>{!state.data?<Loading error={state.error} retry={state.reload}/>:<><ErrorBox error={state.error}/>{state.data.length?<div className="public-tournaments">{state.data.map(t=><Link className="public-tournament" key={t.id} to={`/watch/tournaments/${t.id}`}><span className="muted">Сезон {t.season}</span><h2>{t.name}</h2><p>{dateRange(t.starts_on,t.ends_on)}</p><span>Матчи и расписание<ArrowUpRight/></span></Link>)}</div>:<Empty>Турниров пока нет. Расписание появится здесь, когда организатор добавит матчи.</Empty>}</>}</>}
export function PublicTournamentPage(){const {id}=useParams();return <TournamentContent key={id} id={id!}/>}
function TournamentContent({id}:{id:string}){
 const location=useLocation();const href=location.pathname+location.search;const forward=publicForward(location.state,'tournament',href);const back=publicBack(location.state,href,['calendar'],{href:'/watch/tournaments',label:'← Все турниры'});
 const [params,update]=useQueryPatch();
 const snapshot=isUuid(params.get('snapshot_id'))?params.get('snapshot_id')!:'';
 const state=useLoad(async()=>{const [tournament,matches,standings,fixtures]=await Promise.all([api<PublicTournament>(`/public/tournaments/${id}`),all<PublicMatch>(`/public/tournaments/${id}/matches`),
  api<Standings>(`/public/tournaments/${id}/standings`),all<FixtureView>(`/public/tournaments/${id}/fixtures`)]);return {tournament,matches,standings,fixtures}},id);
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const {tournament:t,matches,standings,fixtures}=state.data;
 // «Таблица» открывается первой у турнира с форматом; общая таблица старых турниров и ссылки с фильтрами расписания ведут на матчи.
 const scheduleLink=['day','hall_id','team_id'].some(k=>params.has(k));
 const first=standings.stages.length&&!standings.implicit&&!scheduleLink?'table':'matches';const raw=params.get('tab')??first;
 const tab=['ratings','teams','matches'].includes(raw)||(raw==='table'&&standings.stages.length)?raw:first;
 const items=[...(standings.stages.length?[{id:'table',label:'Таблица'}]:[]),{id:'matches',label:'Матчи'},{id:'teams',label:'Команды'},{id:'ratings',label:'Рейтинги'}];
 return <><Link className="breadcrumb" to={back.href} state={back.state}>{back.label}</Link><div className="page-head"><div><p className="muted">Сезон {t.season} · {dateRange(t.starts_on,t.ends_on)}</p><h1>{t.name}</h1></div></div>
  <SectionNavigation label="Разделы турнира" items={items} selected={tab}
   onSelect={value=>update({tab:value===first?null:value})} href={value=>`?${patchQuery(params,{tab:value===first?null:value})}`}/>
  <ErrorBox error={state.error}/>
  <div className="tournament-section">{tab==='table'?<StandingsView data={standings} timezone={t.timezone} matchHref={mid=>`/watch/matches/${mid}`} teamHref={team=>`/watch/tournaments/${id}/teams/${team}`}/>
   :tab==='matches'?<><Schedule matches={matches} timezone={t.timezone} matchState={forward} teamHref={team=>`/watch/tournaments/${id}/teams/${team}`} teamState={forward}/><UnscheduledFixtures items={fixtures} title="Ещё без даты"/></>:tab==='teams'?<PublicTournamentTeams tournamentId={id}/>:<TournamentRatings tournamentId={id} publicView initialSnapshot={snapshot}/>}</div></>;
}
