import {useState,useEffect,useRef,type FormEvent} from 'react';
import {Link} from 'react-router-dom';
import {Search,SlidersHorizontal,ChevronLeft,ChevronRight} from 'lucide-react';
import type {PublicMatch,PublicTournament} from '../../../api/domain';
import type {components} from '../../../api/types';
import {api} from '../../../api/client';
import {Loading,ErrorBox,Modal} from '../../../components/ui';
import {useDocumentTitle} from '../../../components/useDocumentTitle';
import {useQueryPatch} from '../../navigation/useQueryPatch';
import {DateNavigation,today} from './DateNavigation';
import {TournamentMatchGroup} from './TournamentMatchGroup';
import {UpcomingMatches,MatchShortList} from './UpcomingMatches';
import {TournamentLeaders} from './TournamentLeaders';
import {usePublicRequest,useWideScreen,useNarrowScreen} from './request';
import './match-center.css';
type Day=components['schemas']['PublicMatchDayPage'];
const STATUSES=[['all','Все'],['live','Идут'],['upcoming','Предстоящие'],['finished','Завершённые']];
function validDay(value:string|null){return !!value&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&!Number.isNaN(Date.parse(value+'T12:00:00Z'))}
const dayLabel=(day:string,options:Intl.DateTimeFormatOptions)=>new Date(day+'T12:00:00Z').toLocaleDateString('ru-RU',{timeZone:'UTC',...options});

export function PublicMatchCenter(){
 const [params,update]=useQueryPatch();const [initialDay]=useState(today);const day=validDay(params.get('day'))?params.get('day')!:initialDay;
 const status=STATUSES.some(([s])=>s===params.get('status'))?params.get('status')!:'all';const tid=params.get('tournament_id')??'';
 const q=params.get('q')??'';const [search,setSearch]=useState(q);const [tick,setTick]=useState(0);
 const wide=useWideScreen();const narrow=useNarrowScreen();const [sheet,setSheet]=useState(false);
 const [tournamentSearch,setTournamentSearch]=useState('');const [catalogQuery,setCatalogQuery]=useState('');
 useEffect(()=>{const timer=setTimeout(()=>setCatalogQuery(tournamentSearch.trim()),250);return()=>clearTimeout(timer)},[tournamentSearch]);
 const tournaments=usePublicRequest<{items:PublicTournament[],total:number}>(`/public/tournaments?limit=100&offset=0${catalogQuery?`&q=${encodeURIComponent(catalogQuery)}`:''}`,tick);
 const filters=new URLSearchParams();for(const key of ['tournament_id','team_id','q']){const value=params.get(key);if(value)filters.set(key,value)}
 const query=new URLSearchParams(filters);query.set('day',day);query.set('status',status);
 // Leaders follow the first tournament of the shown day unless the guest picked one; that guess stays out of the shared link.
 const [firstOfDay,setFirstOfDay]=useState('');const [dayEmpty,setDayEmpty]=useState(false);
 const leaders=tid||params.get('leaders_tournament_id')||firstOfDay;
 useEffect(()=>{const visible=()=>{if(document.visibilityState==='visible')setTick(n=>n+1)};document.addEventListener('visibilitychange',visible);return()=>document.removeEventListener('visibilitychange',visible)},[]);
 useEffect(()=>setSearch(q),[q]);
 useDocumentTitle('Матчи');
 const change=(patch:Record<string,string|null>)=>update({...patch,cursor:null});
 function find(e:FormEvent){e.preventDefault();change({q:search.trim()||null});setSheet(false)}
 const options=tournaments.data?.items??[];
 const tournamentName=tid?options.find(t=>t.id===tid)?.name??'Выбран турнир':'';
 const activeCount=[tid,q,params.get('team_id'),status!=='all'?status:''].filter(Boolean).length;
 const tournamentList=<><input aria-label="Найти турнир" placeholder="Найти турнир" maxLength={200} value={tournamentSearch} onChange={e=>setTournamentSearch(e.target.value)}/><button className={!tid?'selected':''} aria-pressed={!tid} onClick={()=>change({tournament_id:null})}>Все турниры</button>
  {!tournaments.data?<Loading error={tournaments.error} retry={()=>setTick(n=>n+1)}/>:options.map(t=><button key={t.id} className={tid===t.id?'selected':''} aria-pressed={tid===t.id} onClick={()=>change({tournament_id:t.id})}>{t.name}<small>{t.season}</small></button>)}<Link to="/watch/tournaments">Каталог турниров →</Link></>;
 const statusControl=<div className="segmented" role="group" aria-label="Статус матчей">{STATUSES.map(([value,label])=><button key={value} aria-pressed={status===value} onClick={()=>change({status:value==='all'?null:value})}>{label}</button>)}</div>;
 const searchForm=<form onSubmit={find} className="center-search"><input aria-label="Поиск команды или турнира" maxLength={200} value={search} onChange={e=>setSearch(e.target.value)} placeholder="Команда или турнир"/><button aria-label="Найти матчи"><Search/></button></form>;
 return <div className="match-center">{!narrow&&<aside className="center-tournaments"><h2>Турниры</h2>{tournamentList}</aside>}
  <div className="center-main"><div className="center-heading"><h1>Матчи</h1>{narrow
   ?<button className="center-filter-button" aria-haspopup="dialog" onClick={()=>setSheet(true)}><SlidersHorizontal aria-hidden="true"/>Фильтры{activeCount>0&&<span className="center-filter-count" aria-label={`выбрано ${activeCount}`}>{activeCount}</span>}</button>
   :<span className="muted small">Время московское</span>}</div>
  <DateNavigation day={day} onDayChange={d=>change({day:d})}/>
  {!narrow&&<div className="center-filterbar">{statusControl}{searchForm}</div>}
  {activeCount>(narrow?0:status!=='all'?1:0)&&<div className="center-active-filters"><span>{[tournamentName,q,params.has('team_id')?'Выбрана команда':'',narrow&&status!=='all'?STATUSES.find(([s])=>s===status)![1]:''].filter(Boolean).join(' · ')}</span><button className="quiet" onClick={()=>change({tournament_id:null,team_id:null,q:null,status:null})}>Сбросить</button></div>}
  <div className="center-day-list"><DayMatches key={query.toString()} query={query.toString()} filters={filters.toString()} tick={tick} day={day} onFirst={setFirstOfDay} onEmpty={setDayEmpty} onShowDay={d=>change({day:d,status:null})}/></div>
 </div><aside className="center-aside">{wide&&!dayEmpty&&<UpcomingMatches query={filters.toString()} tick={tick}/>}
  <details open={wide} className="center-side-panel center-leaders"><summary>Лидеры турнира</summary>{!tid&&<label className="field"><span>Турнир рейтинга</span><select value={leaders} onChange={e=>update({leaders_tournament_id:e.target.value||null})}><option value="">Выберите турнир</option>{leaders&&!options.some(t=>t.id===leaders)&&<option value={leaders}>Выбранный турнир</option>}{options.map(t=><option key={t.id} value={t.id}>{t.name} · {t.season}</option>)}</select></label>}
   {tid&&<p className="strong">{tournamentName}</p>}{leaders?<TournamentLeaders tournamentId={leaders} tick={tick}/>:<p className="muted">Выберите турнир, чтобы увидеть его лидеров.</p>}
  </details></aside>
  {sheet&&<Modal title="Фильтры" className="center-sheet" onClose={()=>setSheet(false)}>{searchForm}{statusControl}<div className="center-sheet-tournaments"><h3>Турнир</h3>{tournamentList}</div>
   <div className="center-sheet-actions">{activeCount>0&&<button className="quiet" onClick={()=>change({tournament_id:null,team_id:null,q:null,status:null})}>Сбросить</button>}<button className="primary" onClick={()=>setSheet(false)}>Показать матчи</button></div><p className="muted small">Время московское</p></Modal>}
 </div>;
}

function DayMatches({query,filters,tick,day,onFirst,onEmpty,onShowDay}:{query:string,filters:string,tick:number,day:string,onFirst:(id:string)=>void,onEmpty:(empty:boolean)=>void,onShowDay:(d:string)=>void}){
 const [params,update]=useQueryPatch();const [data,setData]=useState<Day>();const [error,setError]=useState<unknown>();const [busy,setBusy]=useState(true);const [retry,setRetry]=useState(0);
 const pages=useRef(1);const pending=useRef<AbortController|null>(null);
 const merge=(old:Day|undefined,page:Day):Day=>old?{...page,tournament_totals:{...old.tournament_totals,...page.tournament_totals},items:[...new Map([...old.items,...page.items].map(m=>[m.id,m])).values()]}:page;
 useEffect(()=>{const controller=new AbortController();pending.current=controller;setBusy(true);setError(undefined);
  // Restore depth from fresh public reads, rather than retaining withdrawn data.
  let depth=pages.current;try{depth=Math.max(depth,Math.min(100,Math.max(1,Number(sessionStorage.getItem(`aifootball:calendar-pages:${query}`))||1)))}catch{}
  void (async()=>{let combined:Day|undefined;let count=0;
   do{const cursor=combined?.next_cursor;const page:Day=await api<Day>(`/public/matches?${query}${cursor?`&cursor=${encodeURIComponent(cursor)}`:''}`,{signal:controller.signal});if(controller.signal.aborted)return;combined=merge(combined,page);count++}while(count<depth&&combined.next_cursor);
   pages.current=count;setData(combined);setBusy(false);
  })().catch(e=>{if(!controller.signal.aborted){setError(e);setBusy(false)}});
  return()=>{controller.abort();pending.current?.abort()};
 },[query,tick,retry]);
 async function more(){if(busy||!data?.next_cursor)return;const controller=new AbortController();pending.current=controller;setBusy(true);setError(undefined);
  try{const page=await api<Day>(`/public/matches?${query}&cursor=${encodeURIComponent(data.next_cursor)}`,{signal:controller.signal});if(controller.signal.aborted)return;pages.current++;setData(old=>merge(old,page));setBusy(false)}catch(e){if(!controller.signal.aborted){setError(e);setBusy(false)}}
 }
 useEffect(()=>{if(data?.items[0])onFirst(data.items[0].tournament.id)},[data?.items[0]?.tournament.id]);
 useEffect(()=>{if(data)onEmpty(!data.items.length)},[data?.items.length]);
 useEffect(()=>{if(data){try{const y=Number(sessionStorage.getItem(`aifootball:calendar-scroll:${query}`));if(y>0)window.scrollTo(0,y)}catch{}}},[!!data]);
 if(!data)return <Loading error={error} retry={()=>setRetry(n=>n+1)}/>;
 if(!data.items.length)return <EmptyDay day={day} data={data} filters={filters} tick={tick} onShowDay={onShowDay}/>;
 const groups=new Map<string,{tournament:PublicTournament,items:PublicMatch[]}>();for(const m of data.items){let group=groups.get(m.tournament.id);if(!group){group={tournament:m.tournament,items:[]};groups.set(m.tournament.id,group)}group.items.push(m)}
 const closed=(params.get('closed')??'').split(',').filter(Boolean);
 return <>{[...groups.values()].map(g=><TournamentMatchGroup key={g.tournament.id} {...g} total={data.tournament_totals[g.tournament.id]??g.items.length} closed={closed.includes(g.tournament.id)} onToggle={()=>update({closed:(closed.includes(g.tournament.id)?closed.filter(id=>id!==g.tournament.id):[...closed,g.tournament.id]).join(',')||null},{replace:true})} onOpen={()=>{try{sessionStorage.setItem(`aifootball:calendar-scroll:${query}`,String(window.scrollY));sessionStorage.setItem(`aifootball:calendar-pages:${query}`,String(pages.current))}catch{}}}/>)}
  <ErrorBox error={error}/>{error&&<button onClick={()=>setRetry(n=>n+1)}>Повторить загрузку матчей</button>}{data.next_cursor&&<button className="center-more" disabled={busy} onClick={()=>void more()}>{busy?'Загружаем…':'Ещё матчи'}</button>}
 </>;
}

// An empty day still answers «what happened and what is next»: neighbouring game days, recent results and the nearest games.
function EmptyDay({day,data,filters,tick,onShowDay}:{day:string,data:Day,filters:string,tick:number,onShowDay:(d:string)=>void}){
 const short=(d:string)=>dayLabel(d,{day:'numeric',month:'long',weekday:'short'});
 return <div className="center-empty-day"><div className="center-empty-head"><p>{dayLabel(day,{day:'numeric',month:'long'})} матчей нет</p>
  {(data.previous_day||data.next_day)&&<div className="center-jump">{data.previous_day&&<button onClick={()=>onShowDay(data.previous_day!)} aria-label={`Предыдущий игровой день: ${short(data.previous_day)}`}><ChevronLeft aria-hidden="true"/>{short(data.previous_day)}</button>}
   {data.next_day&&<button onClick={()=>onShowDay(data.next_day!)} aria-label={`Следующий игровой день: ${short(data.next_day)}`}>{short(data.next_day)}<ChevronRight aria-hidden="true"/></button>}</div>}</div>
  <MatchShortList title="Последние результаты" path={`/public/matches/recent?${filters}`} tick={tick}/>
  <MatchShortList title="Ближайшие матчи" path={`/public/matches/upcoming?${filters}`} tick={tick}/>
 </div>;
}
