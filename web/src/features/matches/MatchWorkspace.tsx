import {scheduleReturn,analysisQueueReturn} from '../navigation/query';
import {useEffect,useState,type ReactNode} from 'react';
import {Link,useParams,useLocation} from 'react-router-dom';
import {ArrowLeft,History} from 'lucide-react';
import {api} from '../../api/client';
import type {Match,Tournament} from '../../api/domain';
import {statuses} from '../../api/domain';
import {Loading,useLoad} from '../../components/ui';
import {SectionNavigation,type SectionItem} from '../../components/match/SectionNavigation';
import {useAuth} from '../auth/Auth';
import {isUuid,readMatchTab} from '../navigation/query';
import {TournamentRail,useCabinetRail} from '../navigation/rail';
import {useQueryPatch} from '../navigation/useQueryPatch';
import {ProtocolSession,SessionChrome,useProtocolSession,useSessionDispatch} from '../protocol/ProtocolSession';
import {ProtocolEditor} from '../protocol/ProtocolEditor';
import {HistoryPanel} from '../protocol/ProtocolPanels';
import {ReviewWorkspace} from '../analysis/ReviewWorkspace';
import {ParticipationEditor} from '../ratings/ParticipationEditor';
import {ActionReview} from '../ratings/ActionReview';
import {MatchPublication} from '../publication/MatchPublication';
import {Lineups,MatchInfo} from './MatchPage';
import {MatchOverview} from './MatchOverview';
import {MatchReportTab} from './MatchReportTab';
import {dateTime} from './timezone';
import './workspace.css';

// Четыре раздела по ходу работы; шаги раздела видны, когда он открыт. Ссылка раздела ведёт на его основной шаг.
const TASKS:SectionItem[]=[{id:'overview',label:'Обзор'},
 {id:'protocol',label:'Протокол',steps:[{id:'info',label:'Сведения'},{id:'lineup',label:'Состав'},{id:'protocol',label:'События'}]},
 {id:'review',label:'Видео',steps:[{id:'review',label:'Проверка'},{id:'participation',label:'Участие'},{id:'actions',label:'Действия'}]},
 {id:'publication',label:'Публикация',steps:[{id:'publication',label:'Опубликовать'},{id:'report',label:'Предпросмотр'}]}];
const ANALYTICS_ONLY=new Set(['participation','actions']);
// Редактирующие задачи делят один экземпляр очереди протокола.
const EDITING=new Set(['protocol','lineup','info','history']);

export function MatchWorkspacePage(){
 const {id=''}=useParams();
 if(!isUuid(id))return <div className="block-error" role="alert">Неверная ссылка на матч.</div>;
 return <MatchWorkspace key={id} matchId={id}/>;
}

export function MatchWorkspace({matchId}:{matchId:string}){
 const location=useLocation();
 const {session}=useAuth();const analytics=Boolean(session?.can_manage_analytics);
 const [params,update]=useQueryPatch();
 const requested=readMatchTab(params,'private');
 const tab=ANALYTICS_ONLY.has(requested)&&!analytics?'overview':requested;
 useEffect(()=>{if(params.get('tab')&&params.get('tab')!==tab&&params.get('tab')!=='overview')update({tab},{replace:true})},[params.get('tab'),tab]);
 const [tick,setTick]=useState(0);
 // Шапка перечитывается при смене задачи: правки протокола видны без общей очереди.
 const match=useLoad(()=>api<Match>(`/matches/${matchId}`),`${matchId}:${tab}:${tick}`);
 const tid=match.data?.tournament_id??'';
 const queueBack=analytics&&tid?analysisQueueReturn(location.state?.analysisReturn,tid):null;
 const tournament=useLoad(async()=>tid?api<Tournament>(`/tournaments/${tid}`):undefined,tid);
 useCabinetRail(tournament.data?<TournamentRail id={tournament.data.id} name={tournament.data.name} active={queueBack?'analysis':'matches'} analytics={analytics}/>:null,[tournament.data?.id,tournament.data?.name,analytics,queueBack]);
 const m=match.data;
 if(!m)return <Loading error={match.error} retry={match.reload}/>;
 const tz=tournament.data?.timezone??'Europe/Moscow';
 const state:Record<string,SectionItem['state']>={info:m.hall_id?undefined:'attention',lineup:m.lineup.length?undefined:'attention',
  protocol:m.protocol.draft?(m.status==='ended'?'attention':undefined):'done',publication:m.published_version_id?'done':undefined};
 // Состояние раздела — по его шагам: хоть один требует внимания → раздел тоже.
 const items=TASKS.map(t=>{const steps=t.steps?.filter(s=>analytics||!ANALYTICS_ONLY.has(s.id)).map(s=>({...s,state:state[s.id]}));
  const own=steps?.some(s=>s.state==='attention')?'attention':state[t.id];return {...t,steps,state:own}});
 return <div className="match-workspace">
  <header className="cabinet-match-head">
   <Link className="icon-button back" to={queueBack??scheduleReturn(location.state?.scheduleReturn,m.tournament_id)} aria-label={queueBack?'К очереди аналитики':'К матчам турнира'}><ArrowLeft/></Link>
   <div className="title"><h1>{m.home.team.name} — {m.away.team.name} <span className={`chip status-chip ${m.status}`}>{statuses[m.status]}</span></h1>
    <p className="muted num">{dateTime(m.scheduled_at,tz)} · {m.hall_snapshot?.name||m.venue_label||'Место не указано'}</p></div>
   <div className="cabinet-head-side">
    <div className="cabinet-score num" aria-label="Текущий счёт протокола в кабинете">{m.projection.effective_score.home??'—'} : {m.projection.effective_score.away??'—'}</div>
    <a className="history-link" href="?tab=history" aria-current={tab==='history'?'page':undefined} onClick={e=>{if(e.metaKey||e.ctrlKey||e.shiftKey||e.button!==0)return;e.preventDefault();update({tab:'history'})}}><History aria-hidden="true"/>История изменений</a>
   </div>
  </header>
  <SectionNavigation label="Задачи матча" items={items} selected={tab} onSelect={value=>update({tab:value})}
   href={value=>`?${new URLSearchParams({tab:value})}`}/>
  <div className="match-task">
   {tab==='overview'&&<MatchOverview match={m} timezone={tz} analytics={analytics}/>}
   {EDITING.has(tab)&&<ProtocolSession matchId={matchId}><EditingTask tab={tab}/></ProtocolSession>}
   {tab==='review'&&<ReviewWorkspace matchId={matchId} actorId={session!.id} canManage={analytics}/>}
   {tab==='participation'&&analytics&&<ParticipationEditor matchId={matchId} actorId={session!.id} onSaved={()=>setTick(n=>n+1)}/>}
   {tab==='actions'&&analytics&&<ActionReview matchId={matchId} actorId={session!.id} onSaved={()=>setTick(n=>n+1)}/>}
   {tab==='report'&&<MatchReportTab match={m} tournament={tournament.data??null} analytics={analytics}/>}
   {tab==='publication'&&<MatchPublication matchId={matchId} tournamentId={m.tournament_id} actorId={session!.id} canManage={analytics}/>}
  </div>
 </div>;
}

function EditingTask({tab}:{tab:string}){
 const state=useProtocolSession();
 if(tab==='protocol')return <ProtocolEditor/>;
 return state.queue?<SessionTask tab={tab}/>:<Loading error={state.error}/>;
}
function SessionTask({tab}:{tab:string}){
 const {queue}=useProtocolSession();const {dispatch}=useSessionDispatch();const m=queue!.view;
 const content:Record<string,ReactNode>={lineup:<Lineups match={m} dispatch={dispatch}/>,info:<MatchInfo match={m} dispatch={dispatch}/>,history:<HistoryPanel match={m}/>};
 return <SessionChrome>{()=>content[tab]}</SessionChrome>;
}
