import {useEffect,useRef,useState,type ReactNode} from 'react';
import {Link,useLocation,useSearchParams} from 'react-router-dom';
import {FileText,Video,Users,ChartColumn,Upload,RefreshCw,Lock,CircleAlert,Check} from 'lucide-react';
import {all,api} from '../../api/client';
import type {AnalysisOverview,Match,Version} from '../../api/domain';
import {ErrorBox,Loading,useLoad} from '../../components/ui';
import {ProtocolSession,useProtocolSession} from '../protocol/ProtocolSession';
import {CommandStatus,useRatingCommand} from '../ratings/commands';
import type {Actions,Analytics,Participation,RatingSnapshot} from '../ratings/types';
import {GuestPreview} from './GuestPreview';
import {cvBlock,performanceBlock,protocolBlock,ratingBlock,when,type PublicationBlock} from './publicationModel';
import './publication.css';

type PerformanceView={revision:number;match_id:string;participation_version_id:string|null;action_version_id:string|null;policy_approved:boolean};

// Экран координирует отдельные существующие операции; общей транзакции и «опубликовать всё» нет.
export function MatchPublication({matchId,tournamentId,actorId,canManage}:{matchId:string;tournamentId:string;actorId:string;canManage:boolean}){
 const [tick,setTick]=useState(0);const refresh=()=>setTick(n=>n+1);
 const match=useLoad(()=>api<Match>(`/matches/${matchId}`),`${matchId}:${tick}`);
 return <div className="publication-layout">
  <section className="surface publication-rows" aria-label="Публикации матча">
   {!match.data?<Loading error={match.error} retry={match.reload}/>:<>
    <ProtocolRow match={match.data} tick={tick} onChanged={refresh}/>
    {canManage&&<CvRow matchId={matchId} actorId={actorId} tick={tick} onChanged={refresh}/>}
    {canManage&&<PerformanceRow match={match.data} actorId={actorId} tick={tick} onChanged={refresh}/>}
    {canManage&&<RatingRow tournamentId={tournamentId} actorId={actorId} tick={tick} onChanged={refresh}/>}
    {!canManage&&<p className="muted small row-note">Видеоанализ, оценки и рейтинг публикует Админ+.</p>}
   </>}
  </section>
  <GuestPreview matchId={matchId} refresh={tick}/>
 </div>;
}

function Row({icon,title,description,block,children,tag}:{icon:ReactNode;title:string;description:string;block:PublicationBlock;children:ReactNode;tag?:string}){
 const location=useLocation();
 return <article className="publication-row">
  <div className="row-icon" aria-hidden="true">{icon}</div>
  <div>{tag&&<div className="row-tag">{tag}</div>}<h3>{title}</h3><p className="muted">{description}</p>
   <dl className="versions num"><dt>На сайте</dt><dd>{block.currentLabel==='Не опубликован'||block.currentLabel==='Источники не разрешены'?<span className="chip">{block.currentLabel}</span>:<span className="chip ok"><Check/>{block.currentLabel}</span>}</dd>
    {block.selectedLabel&&<><dt>Выбрано</dt><dd>{block.selectedLabel}</dd></>}<dt>Что изменится</dt><dd>{block.changeSummary}</dd></dl></div>
  <div className="row-actions">{children}
   {block.blockers.map(b=><p key={b.text} className="blocker"><CircleAlert/><span>{b.text}. <Link state={location.state} to={b.href}>Исправить →</Link></span></p>)}</div>
 </article>;
}

function ProtocolRow({match,tick,onChanged}:{match:Match;tick:number;onChanged:()=>void}){
 const versions=useLoad(()=>all<Version>(`/matches/${match.id}/versions`),`${match.id}:${tick}`);
 const [selected,setSelected]=useState<string>('');const [acting,setActing]=useState<string|null>(null);
 if(!versions.data)return <Loading error={versions.error} retry={versions.reload}/>;
 const list=versions.data;const chosen=selected||list.find(v=>v.id!==match.published_version_id)?.id||list[0]?.id||'';
 const block=protocolBlock(match,list,chosen||null);
 return <Row icon={<FileText/>} title="Официальный протокол" description="Счёт, события и состав матча." block={block}>
  {list.length>0&&<label className="field"><span>Версия протокола</span><select aria-label="Версия протокола" value={chosen} disabled={!!acting} onChange={e=>setSelected(e.target.value)}>{list.map(v=><option key={v.id} value={v.id}>Версия {v.number}{v.id===match.published_version_id?' · на сайте':''}</option>)}</select></label>}
  {acting?<ProtocolSession matchId={match.id}><PublishAction versionId={acting} onDone={ok=>{setActing(null);if(ok)onChanged()}}/></ProtocolSession>
   :<button className="primary" disabled={!chosen||chosen===match.published_version_id} onClick={()=>setActing(chosen)}><Upload/>Опубликовать протокол</button>}
 </Row>;
}

// Очередь протокола создаётся только по нажатию и закрывается после результата.
function PublishAction({versionId,onDone}:{versionId:string;onDone:(ok:boolean)=>void}){
 const {queue,error:loadError}=useProtocolSession();const [error,setError]=useState<unknown>();const sent=useRef(false);
 const waiting=!!queue&&queue.items.length>0&&!sent.current;
 useEffect(()=>{
  if(!queue||sent.current||queue.blocked||queue.items.length)return;
  sent.current=true;
  queue.enqueue({kind:'publish',payload:{version_id:versionId}}).then(()=>onDone(true)).catch(setError);
 },[queue,queue?.blocked,queue?.items.length]);
 // Автоповтор очереди мог доставить команду после потерянного ответа.
 useEffect(()=>{if(sent.current&&error&&queue&&!queue.items.length)onDone(true)},[error,queue?.items.length]);
 if(!queue)return <Loading error={loadError}/>;
 if(queue.blocked)return <div className="blocker"><Lock/><span>Протокол открыт в другом окне. Завершите ввод там или возьмите управление во вкладке <Link to="?tab=protocol">Протокол</Link>.</span><button onClick={()=>onDone(false)}>Закрыть</button></div>;
 if(waiting)return <div className="blocker"><CircleAlert/><span>В протоколе есть неотправленная команда ({queue.items[0].kind}). Новую публикацию не ставим в очередь. <Link to="?tab=protocol">Открыть протокол</Link></span><button onClick={()=>onDone(false)}>Закрыть</button></div>;
 return <div className="publish-progress" role="status">{error?<><ErrorBox error={error}/>
   <div className="row"><button onClick={()=>queue.retry().then(()=>{if(!queue.items.length)onDone(true)}).catch(setError)} disabled={['conflict','invalid'].includes(queue.items[0]?.state??'')}>Повторить тем же запросом</button><button onClick={()=>onDone(false)}>Закрыть</button></div>
   {queue.items[0]&&['conflict','invalid'].includes(queue.items[0].state)&&<p className="small">Конфликт решается во вкладке <Link to="?tab=protocol">Протокол</Link>; команда сохранена.</p>}</>
  :<button className="pending" disabled><Upload/>Публикуем протокол…</button>}</div>;
}

function CvRow({matchId,actorId,tick,onChanged}:{matchId:string;actorId:string;tick:number;onChanged:()=>void}){
 const [params]=useSearchParams();
 const overview=useLoad(()=>api<AnalysisOverview>(`/matches/${matchId}/analysis`),`${matchId}:${tick}`);
 const command=useRatingCommand(`aifootball:analysis-command:v1:${actorId}:${matchId}`,()=>{overview.reload();onChanged()});
 const [selected,setSelected]=useState('');
 if(!overview.data)return <Loading error={overview.error} retry={overview.reload}/>;
 const o=overview.data;const confirmed=o.runs.filter(r=>r.status==='confirmed');
 const requested=params.get('run_id');const chosen=selected||(requested&&o.runs.some(r=>r.id===requested)?requested:'')||o.active_run_id||confirmed[0]?.id||o.runs[0]?.id||'';const run=o.runs.find(r=>r.id===chosen);
 const block=cvBlock(o,chosen||null);
 const can=!!run&&run.status==='confirmed'&&run.passed&&run.id!==o.published_run_id;
 return <Row icon={<Video/>} title="Видеоанализ" description="Карты, физические показатели и передачи по записи матча." block={block}>
  {o.runs.length>0&&<label className="field"><span>Версия видеоанализа</span><select aria-label="Версия видеоанализа" value={chosen} disabled={command.locked} onChange={e=>setSelected(e.target.value)}>{o.runs.map(r=><option key={r.id} value={r.id}>{r.status==='confirmed'?'Подтверждена':'На проверке'} · {when(r.created_at)}{r.id===o.published_run_id?' · на сайте':''}</option>)}</select></label>}
  <button className="primary" disabled={!can||command.locked} onClick={()=>void command.execute(`/matches/${matchId}/analysis/runs/${chosen}/publish`,{expected_revision:run!.revision,expected_analysis_revision:o.analysis_revision})}><Upload/>Опубликовать видеоанализ</button>
  <CommandStatus command={command}/>
 </Row>;
}

function PerformanceRow({match,actorId,tick,onChanged}:{match:Match;actorId:string;tick:number;onChanged:()=>void}){
 const reads=useLoad(async()=>{const [saved,part,actions]=await Promise.all([api<PerformanceView>(`/matches/${match.id}/performance-publication`),
  api<Participation>(`/matches/${match.id}/participation`),api<Actions>(`/matches/${match.id}/performance-actions`)]);return {saved,part,actions}},`${match.id}:${tick}`);
 const command=useRatingCommand(`aifootball:rating-publication:${actorId}:${match.id}`,()=>{reads.reload();onChanged()});
 // Отправленная, но не подтверждённая команда важнее повторного чтения: её выбор показываем как есть.
 const pendingBody=command.pending?.body as {participation_version_id?:string;action_version_id?:string;approve_policy?:boolean}|undefined;
 const [edit,setEdit]=useState<{part?:string;action?:string;approve?:boolean}>({});
 if(!reads.data)return <Loading error={reads.error} retry={reads.reload}/>;
 const {saved,part,actions}=reads.data;
 const partId=pendingBody?.participation_version_id??edit.part??saved.participation_version_id??'';
 const actionId=pendingBody?.action_version_id??edit.action??saved.action_version_id??'';
 const approve=pendingBody?.approve_policy??edit.approve??saved.policy_approved;
 const block=performanceBlock(match,part,actions,saved,{participation_version_id:partId||null,action_version_id:actionId||null,policy_approved:approve});
 return <Row icon={<Users/>} title="Данные для оценок и статистики" description="Какие проверенные версии участия и действий идут в оценки игроков и командную статистику на сайте. При публикации видеоанализа сюда сами ставятся версии из видео, если вы не выбрали свои." block={block}>
  <label className="field"><span>Участие</span><select aria-label="Публикуемая версия участия" disabled={command.locked} value={partId} onChange={e=>setEdit({...edit,part:e.target.value})}><option value="">Не выбрано</option>{part.versions.filter(v=>v.status==='confirmed').map(v=><option key={v.id} value={v.id}>Участие №{v.revision}{v.auto?' · авто по видео':''}</option>)}</select></label>
  <label className="field"><span>Действия</span><select aria-label="Публикуемая версия действий" disabled={command.locked} value={actionId} onChange={e=>setEdit({...edit,action:e.target.value})}><option value="">Не выбрано</option>{actions.versions.filter(v=>v.status==='confirmed').map(v=><option key={v.id} value={v.id}>Действия №{v.revision}{v.auto?' · авто по видео':''}</option>)}</select></label>
  <label className="check"><input type="checkbox" disabled={command.locked} checked={approve} onChange={e=>setEdit({...edit,approve:e.target.checked})}/>Разрешить методику для публичного рейтинга</label>
  <button className="primary" disabled={command.locked||!partId||!actionId} onClick={()=>void command.execute(`/matches/${match.id}/performance-publication`,
   {expected_revision:saved.revision,expected_match_revision:match.revision,participation_version_id:partId,action_version_id:actionId,approve_policy:approve},'PUT')}><Lock/>Сохранить разрешение</button>
  <CommandStatus command={command}/>
 </Row>;
}

function RatingRow({tournamentId,actorId,tick,onChanged}:{tournamentId:string;actorId:string;tick:number;onChanged:()=>void}){
 const analytics=useLoad(()=>api<Analytics>(`/tournaments/${tournamentId}/analytics`),`${tournamentId}:${tick}`);
 const command=useRatingCommand<RatingSnapshot>(`aifootball:rating-command:${actorId}:${tournamentId}`,()=>{analytics.reload();onChanged()});
 if(!analytics.data)return <Loading error={analytics.error} retry={analytics.reload}/>;
 const a=analytics.data;const block=ratingBlock(a,tournamentId);const base=block.candidate??a.snapshots.find(s=>s.scope==='public');
 const settings=(base?.settings??{}) as {profile_id?:string;time_basis?:string;level?:string;cutoff?:string|null};
 return <Row icon={<ChartColumn/>} title="Рейтинг турнира" tag="Общий для турнира" description="Считается по всем опубликованным матчам. Прежний рейтинг виден на сайте, пока не опубликован новый." block={block}>
  <div className="row">
   <button disabled={command.locked} onClick={()=>void command.execute(`/tournaments/${tournamentId}/analytics/calculate`,{expected_revision:a.revision,scope:'public',
    profile_id:settings.profile_id??'per10',time_basis:settings.time_basis??'reviewed_effective',level:settings.level??'amateur',cutoff:settings.cutoff??null})}><RefreshCw/>Пересчитать рейтинг</button>
   <button className="primary" disabled={command.locked||!block.candidate||!!block.candidate.stale} onClick={()=>void command.execute(`/tournaments/${tournamentId}/analytics/publish`,{expected_revision:a.revision,snapshot_id:block.candidate!.snapshot_id})}><Upload/>Опубликовать рейтинг</button>
  </div>
  <Link to={`/tournaments/${tournamentId}?tab=ratings`}>Открыть рейтинг турнира →</Link>
  <CommandStatus command={command}/>
 </Row>;
}
