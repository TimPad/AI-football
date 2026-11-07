import {Link,useParams,useLocation} from 'react-router-dom';
import {useDocumentTitle} from '../../components/useDocumentTitle';
import {all,api} from '../../api/client';
import type {components} from '../../api/types';
import type {PublicMatch} from '../../api/domain';
import {useLoad,Loading,Empty,ErrorBox} from '../../components/ui';
import {TeamCrest} from '../../components/match/MatchHeader';
import {useQueryPatch} from '../navigation/useQueryPatch';
import {isUuid} from '../navigation/query';
import {publicBack,publicForward} from '../navigation/publicContext';
import {Schedule} from './Schedule';
import './profiles.css';
type Team=components['schemas']['PublicTeamView'];
export function PublicTeamPage(){const {id='',teamId=''}=useParams();if(!isUuid(id)||!isUuid(teamId))return <p className="block-error" role="alert">Неверная ссылка на команду.</p>;return <TeamContent key={`${id}:${teamId}`} id={id} teamId={teamId}/>}
function TeamContent({id,teamId}:{id:string,teamId:string}){const location=useLocation();const [params,update]=useQueryPatch();const offset=Math.max(0,Math.floor(Number(params.get('players_offset'))||0));
 const state=useLoad(()=>api<Team>(`/public/tournaments/${id}/teams/${teamId}?limit=50&offset=${offset}`),`${id}:${teamId}:${offset}`);
 const matches=useLoad(()=>all<PublicMatch>(`/public/tournaments/${id}/matches?team_id=${teamId}`),`${id}:${teamId}`);
 useDocumentTitle(state.data?.name);
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const t=state.data;const href=location.pathname+location.search;const forward=publicForward(location.state,'team',href);const back=publicBack(location.state,href,['match','team','tournament','calendar'],{href:`/watch/tournaments/${id}?tab=teams`,label:'← Команды турнира'});
 return <><Link className="breadcrumb" to={back.href} state={back.state}>{back.label}</Link><div className="page-head public-team-title"><TeamCrest name={t.name} logoId={t.logo_id} side="home"/><div><p className="muted">{t.tournament.name}</p><h1>{t.name}</h1></div></div>
  <section className="surface"><h2>Опубликованные игроки</h2><p className="muted">Имена и номера — из опубликованных составов этого турнира.</p>{!t.players.items.length?<Empty>Состав ещё не опубликован</Empty>:<ul className="public-profile-roster">{t.players.items.map(p=><li key={p.player_id}><span className="num">№ {p.shirt_number??'—'}</span><Link to={`/watch/players/${p.player_id}?tournament_id=${id}`} state={forward}>{p.display_name}</Link></li>)}</ul>}{t.players.total>50&&<div className="pager"><button disabled={!offset} onClick={()=>update({players_offset:offset>50?String(offset-50):null})}>Предыдущие игроки</button><span>{offset+1}–{Math.min(offset+50,t.players.total)} из {t.players.total}</span><button disabled={offset+50>=t.players.total} onClick={()=>update({players_offset:String(offset+50)})}>Следующие игроки</button></div>}</section>
  <section className="public-team-matches"><h2>Матчи команды</h2>{!matches.data?<Loading error={matches.error} retry={matches.reload}/>:<><ErrorBox error={matches.error}/><Schedule wholeRow matches={matches.data} timezone={t.tournament.timezone} matchState={forward} teamHref={team=>`/watch/tournaments/${id}/teams/${team}`} teamState={forward} teamFilter={false}/></>}</section>
 </>;
}
export function PublicTournamentTeams({tournamentId}:{tournamentId:string}){const location=useLocation();const state=useLoad(()=>all<components['schemas']['PublicTeamSummary']>(`/public/tournaments/${tournamentId}/teams`),tournamentId);const forward=publicForward(location.state,'tournament',location.pathname+location.search);
 return !state.data?<Loading error={state.error} retry={state.reload}/>:state.data.length?<div className="public-profile-teams">{state.data.map(t=><Link className="surface" key={t.id} to={`/watch/tournaments/${tournamentId}/teams/${t.id}`} state={forward}><TeamCrest name={t.name} logoId={t.logo_id} side="home"/><h2>{t.name}</h2><span className="muted">Состав и матчи →</span></Link>)}</div>:<Empty>Команды пока не добавлены.</Empty>;
}
