import {useState} from 'react';
import {useDocumentTitle} from '../../components/useDocumentTitle';
import {Link,useLocation,useParams} from 'react-router-dom';
import {api,ApiError} from '../../api/client';
import type {components} from '../../api/types';
import {useLoad,Loading,Empty} from '../../components/ui';
import {useQueryPatch} from '../navigation/useQueryPatch';
import {isUuid} from '../navigation/query';
import {publicBack} from '../navigation/publicContext';
import {PlayerRatingHistory} from '../ratings/PlayerRatingHistory';
import './profiles.css';
type Profile=components['schemas']['PublicPlayerProfile'];
export function PublicPlayerPage(){const {id=''}=useParams();if(!isUuid(id))return <p className="block-error" role="alert">Неверная ссылка на игрока.</p>;return <PlayerContent key={id} id={id}/>}
function PlayerContent({id}:{id:string}){const location=useLocation();const [params,update]=useQueryPatch();const [ratingName,setRatingName]=useState<string|null>(null);
 const tid=isUuid(params.get('tournament_id'))?params.get('tournament_id')!:'';const snapshot=isUuid(params.get('snapshot_id'))?params.get('snapshot_id')!:'';
 const offset=Math.max(0,Math.floor(Number(params.get('appearances_offset'))||0));const teamsOffset=Math.max(0,Math.floor(Number(params.get('teams_offset'))||0));
 const state=useLoad(()=>api<Profile>(`/public/players/${id}?limit=50&offset=${offset}&teams_offset=${teamsOffset}${tid?`&tournament_id=${tid}`:''}`),`${id}:${tid}:${offset}:${teamsOffset}`);
 const back=publicBack(location.state,location.pathname+location.search,['match','team','tournament','calendar'],{href:tid?`/watch/tournaments/${tid}`:'/watch/tournaments',label:'← К турнирам'});
 useDocumentTitle(state.data?.display_name??ratingName);
 return <div className="player-history-page"><Link className="breadcrumb" to={back.href} state={back.state}>{back.label}</Link><h1>{state.data?.display_name??ratingName??'Игрок'}</h1><p className="muted">Публичная карточка по опубликованным протоколам</p>
  {!state.data?(state.error instanceof ApiError&&state.error.status===404?<section className="surface"><Empty>В этом контексте нет опубликованного состава. Доступные издания оценок можно посмотреть ниже.</Empty></section>:<Loading error={state.error} retry={state.reload}/>):<><section className="surface"><h2>Команды и турниры</h2><ul className="public-profile-roster">{state.data.teams.items.map(t=><li key={`${t.tournament_id}:${t.team_id}`}><Link state={back.state} to={`/watch/tournaments/${t.tournament_id}/teams/${t.team_id}`}>{t.team_name}</Link><Link className="muted" state={back.state} to={`/watch/tournaments/${t.tournament_id}`}>{t.tournament_name}</Link></li>)}</ul>{state.data.teams.total>100&&<div className="pager"><button disabled={!teamsOffset} onClick={()=>update({teams_offset:teamsOffset>100?String(teamsOffset-100):null})}>Предыдущие команды</button><button disabled={teamsOffset+100>=state.data.teams.total} onClick={()=>update({teams_offset:String(teamsOffset+100)})}>Следующие команды</button></div>}</section>
   <section className="surface"><h2>Опубликованные выступления</h2><p className="muted">Каждый матч сохраняет имя и номер своего опубликованного состава.</p><ul className="public-profile-appearances">{state.data.appearances.items.map(a=><li key={a.match_id}><div><b>{a.display_name}</b><span className="muted">№ {a.shirt_number??'—'} · {a.team_name}</span></div><span className="muted">{new Date(a.scheduled_at).toLocaleString('ru-RU',{timeZone:a.timezone})} · {a.tournament_name}</span><Link to={`/watch/matches/${a.match_id}?tab=players&player_id=${id}&origin=protocol`} state={back.state}>Открыть матч →</Link></li>)}</ul>{state.data.appearances.total>50&&<div className="pager"><button disabled={!offset} onClick={()=>update({appearances_offset:offset>50?String(offset-50):null})}>Предыдущие матчи</button><span>{offset+1}–{Math.min(offset+50,state.data.appearances.total)} из {state.data.appearances.total}</span><button disabled={offset+50>=state.data.appearances.total} onClick={()=>update({appearances_offset:String(offset+50)})}>Следующие матчи</button></div>}</section></>}
  <PlayerRatingHistory key={`${id}:${tid}:${snapshot}`} playerId={id} publicView initialTournament={tid} initialSnapshot={snapshot} onName={setRatingName} onContext={(t,s)=>{if(t!==tid||s!==snapshot)update({tournament_id:t||null,snapshot_id:s||null,...(t!==tid?{appearances_offset:null,teams_offset:null}:{})},{replace:true})}}/>
 </div>;
}
