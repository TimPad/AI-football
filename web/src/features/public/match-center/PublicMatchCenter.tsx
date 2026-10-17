import {useState,useEffect,type FormEvent} from 'react';
import {Link} from 'react-router-dom';
import {Search,RefreshCw} from 'lucide-react';
import type {PublicMatch,PublicTournament} from '../../../api/domain';
import type {components} from '../../../api/types';
import {api} from '../../../api/client';
import {Loading,ErrorBox,Empty} from '../../../components/ui';
import {useQueryPatch} from '../../navigation/useQueryPatch';
import {DateNavigation,today} from './DateNavigation';
import {TournamentMatchGroup} from './TournamentMatchGroup';
import {UpcomingMatches} from './UpcomingMatches';
import {TournamentLeaders} from './TournamentLeaders';
import {usePublicRequest,useWideScreen} from './request';
import './match-center.css';
type Day=components['schemas']['PublicMatchDayPage'];
const STATUSES=[['all','Все'],['live','Идут'],['upcoming','Предстоящие'],['finished','Завершённые']];
function validDay(value:string|null){return !!value&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&!Number.isNaN(Date.parse(value+'T12:00:00Z'))}

export function PublicMatchCenter(){
 const [params,update]=useQueryPatch();const [initialDay]=useState(today);const day=validDay(params.get('day'))?params.get('day')!:initialDay;
 const status=STATUSES.some(([s])=>s===params.get('status'))?params.get('status')!:'all';const tid=params.get('tournament_id')??'';
 const q=params.get('q')??'';const [search,setSearch]=useState(q);const [tick,setTick]=useState(0);
 const wide=useWideScreen();const [tournamentSearch,setTournamentSearch]=useState('');const [catalogQuery,setCatalogQuery]=useState('');
 useEffect(()=>{const timer=setTimeout(()=>setCatalogQuery(tournamentSearch.trim()),250);return()=>clearTimeout(timer)},[tournamentSearch]);
 const tournaments=usePublicRequest<{items:PublicTournament[],total:number}>(`/public/tournaments?limit=100&offset=0${catalogQuery?`&q=${encodeURIComponent(catalogQuery)}`:''}`,tick);
 const filters=new URLSearchParams();for(const key of ['tournament_id','team_id','q']){const value=params.get(key);if(value)filters.set(key,value)}
 const query=new URLSearchParams(filters);query.set('day',day);query.set('status',status);
 const leaders=tid||params.get('leaders_tournament_id')||'';
 useEffect(()=>{const visible=()=>{if(document.visibilityState==='visible')setTick(n=>n+1)};document.addEventListener('visibilitychange',visible);return()=>document.removeEventListener('visibilitychange',visible)},[]);
 useEffect(()=>setSearch(q),[q]);
 const change=(patch:Record<string,string|null>)=>update({...patch,cursor:null});
 function find(e:FormEvent){e.preventDefault();change({q:search.trim()||null})}
 const options=tournaments.data?.items??[];
 return <div className="match-center"><aside className="center-tournaments"><h2>Турниры</h2><input aria-label="Найти турнир" placeholder="Найти турнир" maxLength={200} value={tournamentSearch} onChange={e=>setTournamentSearch(e.target.value)}/><button className={!tid?'selected':''} onClick={()=>change({tournament_id:null})}>Все турниры</button>
  {!tournaments.data?<Loading error={tournaments.error} retry={()=>setTick(n=>n+1)}/>:options.map(t=><button key={t.id} className={tid===t.id?'selected':''} onClick={()=>change({tournament_id:t.id})}>{t.name}<small>{t.season}</small></button>)}<Link to="/watch/tournaments">Каталог турниров →</Link>
 </aside><div className="center-main"><div className="center-heading"><h1>Матчи</h1><span className="muted small">Время московское</span><button className="quiet" aria-label="Обновить матчи" onClick={()=>setTick(n=>n+1)}><RefreshCw/></button></div>
  <DateNavigation day={day} onDayChange={d=>change({day:d})}/><div className="center-filterbar"><div className="segmented" aria-label="Статус матчей">{STATUSES.map(([value,label])=><button key={value} aria-pressed={status===value} onClick={()=>change({status:value==='all'?null:value})}>{label}</button>)}</div>
  <form onSubmit={find} className="center-search"><input aria-label="Поиск команды или турнира" maxLength={200} value={search} onChange={e=>setSearch(e.target.value)} placeholder="Команда или турнир"/><button aria-label="Найти матчи"><Search/></button></form></div>
  {(tid||q||params.has('team_id'))&&<div className="center-active-filters"><span>{tid?options.find(t=>t.id===tid)?.name??'Выбран турнир':'Все турниры'}{q?` · ${q}`:''}{params.has('team_id')?' · Выбрана команда':''}</span><button className="quiet" onClick={()=>change({tournament_id:null,team_id:null,q:null,status:null})}>Сбросить фильтры</button></div>}
  <div className="center-day-list"><DayMatches key={query.toString()} query={query.toString()} tick={tick} day={day} onFirst={id=>{if(!leaders)update({leaders_tournament_id:id},{replace:true})}}/></div>
 </div><aside className="center-aside"><UpcomingMatches query={filters.toString()} tick={tick} onShowDay={d=>change({day:d,status:null})}/>
  <details open={wide} className="center-side-panel center-leaders"><summary>Лидеры турнира</summary>{!tid&&<label className="field"><span>Турнир рейтинга</span><select value={leaders} onChange={e=>update({leaders_tournament_id:e.target.value||null})}><option value="">Выберите турнир</option>{leaders&&!options.some(t=>t.id===leaders)&&<option value={leaders}>Выбранный турнир</option>}{options.map(t=><option key={t.id} value={t.id}>{t.name} · {t.season}</option>)}</select></label>}
   {tid&&<p className="strong">{options.find(t=>t.id===tid)?.name??'Выбранный турнир'}</p>}{leaders?<TournamentLeaders tournamentId={leaders} tick={tick}/>:<p className="muted">Выберите турнир, чтобы увидеть его лидеров.</p>}
  </details></aside></div>;
}

function DayMatches({query,tick,day,onFirst}:{query:string,tick:number,day:string,onFirst:(id:string)=>void}){
 const [params,update]=useQueryPatch();const [cursor,setCursor]=useState('');const [data,setData]=useState<Day>();const [error,setError]=useState<unknown>();const [busy,setBusy]=useState(true);const [retry,setRetry]=useState(0);
 useEffect(()=>{const controller=new AbortController();setBusy(true);setError(undefined);
  api<Day>(`/public/matches?${query}${cursor?`&cursor=${encodeURIComponent(cursor)}`:''}`,{signal:controller.signal}).then(page=>{if(controller.signal.aborted)return;setData(old=>cursor&&old?{...page,tournament_totals:{...old.tournament_totals,...page.tournament_totals},items:[...new Map([...old.items,...page.items].map(m=>[m.id,m])).values()]}:page);setBusy(false)}).catch(e=>{if(!controller.signal.aborted){setError(e);setBusy(false)}});return()=>controller.abort();
 },[query,cursor,tick,retry]);
 useEffect(()=>{if(data?.items[0])onFirst(data.items[0].tournament.id)},[data?.items[0]?.tournament.id]);
 useEffect(()=>{if(data&&!cursor){try{const y=Number(sessionStorage.getItem(`aifootball:calendar-scroll:${query}`));if(y>0)window.scrollTo(0,y)}catch{}}},[!!data]);
 if(!data)return <Loading error={error} retry={()=>setRetry(n=>n+1)}/>;
 const groups=new Map<string,{tournament:PublicTournament,items:PublicMatch[]}>();for(const m of data.items){let group=groups.get(m.tournament.id);if(!group){group={tournament:m.tournament,items:[]};groups.set(m.tournament.id,group)}group.items.push(m)}
 const closed=(params.get('closed')??'').split(',').filter(Boolean);
 return <><div className="center-count muted small">Найдено: {data.total} · Получено в {new Date(data.generated_at).toLocaleTimeString('ru-RU',{timeZone:'Europe/Moscow',hour:'2-digit',minute:'2-digit'})}</div>
  {!data.items.length?<Empty>{new Date(day+'T12:00:00Z').toLocaleDateString('ru-RU',{day:'numeric',month:'long'})} матчей нет. Выберите другой день или измените фильтры.</Empty>:[...groups.values()].map(g=><TournamentMatchGroup key={g.tournament.id} {...g} total={data.tournament_totals[g.tournament.id]??g.items.length} closed={closed.includes(g.tournament.id)} onToggle={()=>update({closed:(closed.includes(g.tournament.id)?closed.filter(id=>id!==g.tournament.id):[...closed,g.tournament.id]).join(',')||null},{replace:true})} onOpen={()=>{try{sessionStorage.setItem(`aifootball:calendar-scroll:${query}`,String(window.scrollY))}catch{}}}/>)}
  <ErrorBox error={error}/>{error&&<button onClick={()=>setRetry(n=>n+1)}>Повторить загрузку матчей</button>}{data.next_cursor&&<button className="center-more" disabled={busy} onClick={()=>setCursor(data.next_cursor!)}>{busy?'Загружаем…':'Ещё матчи'}</button>}
 </>;
}
