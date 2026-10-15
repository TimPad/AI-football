import {useState} from 'react';
import {Link,useParams,useSearchParams} from 'react-router-dom';
import {Plus,ArrowUpRight} from 'lucide-react';
import {all,api} from '../../api/client';
import type {Match,Roster,Tournament,Entry,RegVersion} from '../../api/domain';
import {ErrorBox,Loading,Empty,Modal,useLoad} from '../../components/ui';
import {useAuth} from '../auth/Auth';
import {TOURNAMENT_TABS,TournamentRail,useCabinetRail,type TournamentTab} from '../navigation/rail';
import {Schedule,type ScheduleItem} from '../public/Schedule';
import {TournamentRatings} from '../ratings/TournamentRatings';
import {MatchCreateForm} from '../matches/MatchForms';
import {TournamentSettings} from './TournamentList';
import {Entries,Rules,type Data} from './TournamentPage';
import {TournamentPublicationList} from './TournamentPublicationList';
import './workspace.css';

const TITLES:Record<TournamentTab,string>={matches:'Матчи',ratings:'Рейтинги',publication:'Публикация',teams:'Команды',
 players:'Игроки',halls:'Залы',rules:'Регламент',info:'Сведения'};

// Кабинетный календарь показывает текущий частный счёт протокола; шапка помечает это как кабинет.
export function scheduleFromPrivate(m:Match):ScheduleItem{
 return {id:m.id,scheduled_at:m.scheduled_at,schedule_slot_s:(m.regulation_override??m.regulation.rules).schedule_slot_s,
  venue_label:m.venue_label,hall:m.hall_snapshot?{id:m.hall_snapshot.id,name:m.hall_snapshot.name,address:m.hall_snapshot.address,
   pitch_length_m:m.hall_snapshot.pitch_length_m,pitch_width_m:m.hall_snapshot.pitch_width_m}:null,
  home_name:m.home.team.name,away_name:m.away.team.name,status:m.status,score:{home:m.projection.effective_score.home??null,away:m.projection.effective_score.away??null},
  broadcast_url:m.broadcast_url??null,broadcast_embed_url:m.broadcast_embed_url??null};
}

export function TournamentPage(){const {id}=useParams();return <TournamentWorkspace key={id} tournamentId={id!}/>}

export function TournamentWorkspace({tournamentId:id}:{tournamentId:string}){
 const {session}=useAuth();const [params]=useSearchParams();
 const raw=params.get('tab');const tab:TournamentTab=(TOURNAMENT_TABS as readonly string[]).includes(raw??'')?raw as TournamentTab:'matches';
 const state=useLoad(async()=>{const [t,entries,rules,matches]=await Promise.all([api<Tournament>(`/tournaments/${id}`),all<Entry>(`/tournaments/${id}/entries`),
  all<RegVersion>(`/tournaments/${id}/regulations`),all<Match>(`/tournaments/${id}/matches`)]);return {t,entries,rules,matches}},id);
 const analytics=Boolean(session?.can_manage_analytics);
 useCabinetRail(state.data?<TournamentRail id={id} name={state.data.t.name} active={tab} analytics={analytics}/>:null,[id,tab,analytics,state.data?.t.name]);
 const [create,setCreate]=useState(false);const [error,setError]=useState<unknown>();
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const d=state.data;
 async function archive(){try{await api(`/tournaments/${id}`,{method:'PATCH',body:JSON.stringify({archived:!d.t.archived,expected_revision:d.t.revision})});state.reload()}catch(e){setError(e)}}
 const canCreate=!d.t.archived&&d.rules.length>0&&d.entries.length>=2;
 return <div className="tournament-workspace">
  <div className="page-head"><div><h1>{TITLES[tab]}</h1><p className="muted">{d.t.name}{d.t.archived?' · архив':''} · Сезон {d.t.season}</p></div>
   <div className="row">{tab==='matches'&&<button className="primary" disabled={!canCreate} onClick={()=>setCreate(true)}><Plus/>Создать матч</button>}
    <Link className="public-action" to={`/watch/tournaments/${d.t.id}`}>Страница для зрителей<ArrowUpRight/></Link></div></div>
  <ErrorBox error={error}/>
  {tab==='matches'&&(!canCreate&&!d.matches.length?<Empty>Для первого матча добавьте регламент и минимум две команды.</Empty>
   :<Schedule matches={d.matches.map(scheduleFromPrivate)} timezone={d.t.timezone} matchHref={mid=>`/matches/${mid}`}/>)}
  {tab==='ratings'&&(analytics?<TournamentRatings tournamentId={id} actorId={session!.id}/>:<Empty>Рейтинги доступны Админ+.</Empty>)}
  {tab==='publication'&&<TournamentPublicationList data={d} analytics={analytics}/>}
  {tab==='teams'&&<Entries tid={id} data={d} onSaved={state.reload}/>}
  {tab==='players'&&<TournamentPlayers data={d}/>}
  {tab==='halls'&&<TournamentHalls data={d}/>}
  {tab==='rules'&&<Rules key={d.rules.map(r=>r.id).join()} tid={id} data={d} onSaved={state.reload}/>}
  {tab==='info'&&<section className="surface"><h2>Сведения о турнире</h2><TournamentSettings value={d.t} onSaved={state.reload}/><hr/>
   <button className="quiet" onClick={archive}>{d.t.archived?'Вернуть из архива':'Архивировать турнир'}</button></section>}
  {create&&<Modal title="Новый матч" onClose={()=>setCreate(false)}><MatchCreateForm tournament={d.t} entries={d.entries} rules={d.rules} onSaved={()=>{setCreate(false);state.reload()}}/></Modal>}
 </div>;
}

// Игроки турнира — из заявок; редактирование в существующих формах заявки и справочника.
function TournamentPlayers({data:d}:{data:Data}){
 const rosters=useLoad(()=>Promise.all(d.entries.map(e=>api<Roster>(`/entries/${e.id}/players`))),d.entries.map(e=>e.id).join());
 if(!d.entries.length)return <Empty>В турнире пока нет команд. Добавьте их на странице «Команды».</Empty>;
 if(!rosters.data)return <Loading error={rosters.error} retry={rosters.reload}/>;
 return <section className="surface"><div className="panel-head"><div><h2>Игроки турнира</h2><p className="muted">Заявки команд этого турнира. Личность — запись справочника.</p></div><Link to="/players">Справочник игроков →</Link></div>
  {rosters.data.map(r=><div key={r.id} className="roster-block"><div className="row"><h3>{r.team.name}</h3><Link to={`/tournaments/${d.t.id}/teams/${r.id}`}>Изменить заявку →</Link></div>
   {r.players.filter(p=>p.active).length?<div className="table-scroll"><table><thead><tr><th>Номер</th><th>Игрок</th><th>Амплуа в справочнике</th></tr></thead><tbody>
    {r.players.filter(p=>p.active).map(p=><tr key={p.id}><td className="num">{p.shirt_number??'—'}</td><td>{p.player.name}</td><td className="muted">{p.player.position??'—'}</td></tr>)}</tbody></table></div>
   :<p className="muted">Заявка пуста.</p>}</div>)}</section>;
}

// Залы турнира — те, что указаны в расписании; редактор зала общий.
function TournamentHalls({data:d}:{data:Data}){
 const halls=new Map<string,{id:string;name:string;address:string;count:number}>();
 for(const m of d.matches)if(m.hall_snapshot){const h=m.hall_snapshot;const v=halls.get(h.id);halls.set(h.id,{id:h.id,name:h.name,address:h.address,count:(v?.count??0)+1})}
 return <section className="surface"><div className="panel-head"><div><h2>Залы турнира</h2><p className="muted">Площадки из расписания матчей.</p></div><Link to="/halls">Все залы →</Link></div>
  {halls.size?<div className="table-scroll"><table><thead><tr><th>Зал</th><th>Адрес</th><th>Матчей</th><th/></tr></thead><tbody>{[...halls.values()].map(h=>
   <tr key={h.id}><td className="strong">{h.name}</td><td>{h.address}</td><td className="num">{h.count}</td><td><Link to={`/halls/${h.id}`}>Открыть зал →</Link></td></tr>)}</tbody></table></div>
  :<Empty>В расписании пока нет залов.</Empty>}</section>;
}
