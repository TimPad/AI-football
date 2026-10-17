import {TournamentAnalysisQueue} from '../analysis/TournamentAnalysisQueue';
import {protocolPublicationState} from './readiness';
import {ApplicationSettings} from '../captain/TournamentApplications';
import {useState} from 'react';
import {Link,useParams} from 'react-router-dom';
import {Plus,ArrowUpRight} from 'lucide-react';
import {all,api} from '../../api/client';
import type {Match,Tournament,Entry,RegVersion} from '../../api/domain';
import {ErrorBox,Loading,Empty,Modal,useLoad} from '../../components/ui';
import {useAuth} from '../auth/Auth';
import {TournamentRail,readTournamentTab,useCabinetRail,type TournamentTab} from '../navigation/rail';
import {SectionNavigation} from '../../components/match/SectionNavigation';
import {useQueryPatch} from '../navigation/useQueryPatch';
import {Schedule,type ScheduleItem} from '../public/Schedule';
import {TournamentRatings} from '../ratings/TournamentRatings';
import {MatchCreateForm} from '../matches/MatchForms';
import {TournamentSettings} from './TournamentList';
import {Entries,Rules} from './TournamentPage';
import {TournamentOverview} from './TournamentOverview';
import './workspace.css';

const TITLES:Record<TournamentTab,string>={analysis:'Обработка',matches:'Матчи',ratings:'Рейтинги',teams:'Команды',rules:'Настройки',info:'Настройки'};

// Кабинетный календарь показывает текущий частный счёт протокола; шапка помечает это как кабинет.
export function scheduleFromPrivate(m:Match):ScheduleItem{
 return {id:m.id,scheduled_at:m.scheduled_at,schedule_slot_s:(m.regulation_override??m.regulation.rules).schedule_slot_s,
  venue_label:m.venue_label,hall:m.hall_snapshot?{id:m.hall_snapshot.id,name:m.hall_snapshot.name,address:m.hall_snapshot.address,
   pitch_length_m:m.hall_snapshot.pitch_length_m,pitch_width_m:m.hall_snapshot.pitch_width_m}:null,
  home_name:m.home.team.name,away_name:m.away.team.name,status:m.status,score:{home:m.projection.effective_score.home??null,away:m.projection.effective_score.away??null},
  broadcast_url:m.broadcast_url??null,broadcast_embed_url:m.broadcast_embed_url??null};
}

const SETTINGS=[{id:'rules',label:'Регламент'},{id:'info',label:'Сведения о турнире'}];

// Публикация матча — отметкой в строке расписания: не нужен отдельный раздел «Публикация».
function onSite(m:Match,scheduleReturn:string){
 const state=protocolPublicationState(m);
 if(state==='new_version')return <Link className="chip warn" state={{scheduleReturn}} to={`/matches/${m.id}?tab=publication`}>Есть новая версия →</Link>;
 if(state==='ready')return <Link className="chip warn" state={{scheduleReturn}} to={`/matches/${m.id}?tab=publication`}>Готов к публикации →</Link>;
 if(m.published_version_id)return <span className="chip ok">{m.published_analysis_run_id?'На сайте · видео':'На сайте'}</span>;
 return m.status==='ended'?<span className="chip warn">Не на сайте</span>:null;
}

export function TournamentPage(){const {id}=useParams();return <TournamentWorkspace key={id} tournamentId={id!}/>}

export function TournamentWorkspace({tournamentId:id}:{tournamentId:string}){
 const {session}=useAuth();const [params,update]=useQueryPatch();
 const tab=readTournamentTab(params.get('tab'));
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
  <TournamentOverview data={d} onSaved={state.reload}/>
  {tab==='matches'&&(!canCreate&&!d.matches.length?<Empty>Для первого матча добавьте регламент и минимум две команды.</Empty>
   :<Schedule matches={d.matches.map(scheduleFromPrivate)} timezone={d.t.timezone} matchHref={mid=>`/matches/${mid}`} matchState={{scheduleReturn:`/tournaments/${id}?${params.toString()}`}} extra={mid=>onSite(d.matches.find(m=>m.id===mid)!,`/tournaments/${id}?${params.toString()}`)}/>)}
  {tab==='analysis'&&(analytics?<TournamentAnalysisQueue tournamentId={id} timezone={d.t.timezone}/>:<Empty>Очередь обработки доступна Админ+.</Empty>)}
  {tab==='ratings'&&(analytics?<TournamentRatings tournamentId={id} actorId={session!.id}/>:<Empty>Рейтинги доступны Админ+.</Empty>)}
  {tab==='teams'&&<Entries tid={id} data={d} onSaved={state.reload}/>}
  {(tab==='rules'||tab==='info')&&<SectionNavigation label="Настройки турнира" items={SETTINGS} selected={tab} onSelect={value=>update({tab:value})}
   href={value=>`?tab=${value}`}/>}
  {tab==='rules'&&<Rules key={d.rules.map(r=>r.id).join()} tid={id} data={d} onSaved={state.reload}/>}
  {tab==='info'&&<><section className="surface"><h2>Сведения о турнире</h2><TournamentSettings value={d.t} onSaved={state.reload}/><hr/>
   <button className="quiet" onClick={archive}>{d.t.archived?'Вернуть из архива':'Архивировать турнир'}</button></section><ApplicationSettings key={d.t.revision} tournament={d.t} onSaved={state.reload}/></>}
  {create&&<Modal title="Новый матч" onClose={()=>setCreate(false)}><MatchCreateForm tournament={d.t} entries={d.entries} rules={d.rules} onSaved={()=>{setCreate(false);state.reload()}}/></Modal>}
 </div>;
}
