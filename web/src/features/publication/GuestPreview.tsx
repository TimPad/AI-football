import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {ExternalLink,FileText,Video,ChartColumn} from 'lucide-react';
import {api,errorText} from '../../api/client';
import type {PublicMatch} from '../../api/domain';
import {TeamCrest} from '../../components/match/MatchHeader';
import {loadPublicSection} from '../public/matchLoader';
import type {ReportModel} from '../match-report/model';

type Sources=Partial<Pick<ReportModel,'protocol'|'cv'|'ratings'>>;

// Только публичные маршруты — то, что видит гость, даже если открыл вошедший администратор.
export function GuestPreview({matchId,refresh=0}:{matchId:string;refresh?:number}){
 const [match,setMatch]=useState<PublicMatch|null>(null);const [sources,setSources]=useState<Sources>({});const [error,setError]=useState('');
 useEffect(()=>{
  const controller=new AbortController();setError('');
  api<PublicMatch>(`/public/matches/${matchId}`,{signal:controller.signal}).then(async m=>{
   if(controller.signal.aborted)return;setMatch(m);
   const value=await loadPublicSection(m,'overview',null,controller.signal);if(!controller.signal.aborted)setSources(value);
  }).catch(e=>{if(!controller.signal.aborted)setError(errorText(e))});
  return()=>controller.abort();
 },[matchId,refresh]);
 const line=(label:string,icon:React.ReactNode,text:string)=><div>{icon}<span>{label}</span><span className="v num">{text}</span></div>;
 const p=sources.protocol,c=sources.cv,r=sources.ratings;
 return <aside className="surface guest-preview" aria-label="Сейчас видит зритель">
  <div className="guest-head"><h3>Сейчас видит зритель</h3><Link to={`/watch/matches/${matchId}`} target="_blank" aria-label="Открыть как зритель"><ExternalLink/></Link></div>
  <p className="muted small">Только опубликованные источники. Черновики и выбранные версии здесь не видны.</p>
  {error?<p className="block-error" role="alert">{error}</p>:!match?<p className="muted">Загружаем…</p>:<>
   <div className="guest-score num"><TeamCrest name={match.home_name} logoId={match.home_logo_id} side="home" size="sm"/><span>{match.home_name}</span>
    <b>{match.score.home==null?'— : —':`${match.score.home} : ${match.score.away}`}</b><span>{match.away_name}</span><TeamCrest name={match.away_name} logoId={match.away_logo_id} side="away" size="sm"/></div>
   <div className="guest-sources">
    {line('Протокол',<FileText/>,p?.status==='ready'?`версия ${p.value.number}`:p?.status==='error'?'ошибка загрузки':p?'не опубликован':'…')}
    {line('Видеоанализ',<Video/>,c?.status==='ready'?`${c.value.partial?'фрагмент':'весь матч'} · ${Math.round(c.value.processed_s)} с`:c?.status==='error'?'ошибка загрузки':c?'не опубликован':'…')}
    {line('Оценки игроков',<ChartColumn/>,r?.status==='ready'?`издание ${r.value.snapshot_id?.slice(0,8)}`:r?.status==='error'?'ошибка загрузки':r?'не опубликованы':'…')}
   </div></>}
  <p className="notice-info small">Каждая публикация — отдельная операция. Общей кнопки и общей транзакции нет.</p>
  <Link className="button" to={`/watch/matches/${matchId}`} target="_blank"><ExternalLink/>Открыть как зритель</Link>
 </aside>;
}
