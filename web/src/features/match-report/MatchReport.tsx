import type {ReactNode} from 'react';
import {Link} from 'react-router-dom';
import type {MatchRatingsView,PublicAnalysis,PublicMatch} from '../../api/domain';
import {PitchMap} from '../../components/pitch/PitchMap';
import {YandexMapsLink} from '../../components/YandexMapsLink';
import {sharedHeatmapMax} from '../../components/pitch/heatmap';
import {PlayerInspector} from '../../components/match/PlayerInspector';
import {SourceStatus} from '../../components/match/SourceStatus';
import {PublicProtocolContent,PublicLineups} from '../protocol/PublicProtocolContent';
import {roles,reason,num} from '../ratings/types';
import {canAttachCurrentCv,mergeRoster,periodLabel,type RosterRow} from './adapters';
import type {PlayerSelection,ReportModel,Resource} from './model';
import {STAT_GROUPS,formatFact,type StatGroup} from './facts';
import {PlayerTable} from './PlayerTable';
import {TeamComparison} from './TeamComparison';
import './report.css';

type RatingRow=MatchRatingsView['items'][number];
type Props={match:PublicMatch;model:ReportModel;section:string;group:StatGroup;selection:PlayerSelection|null;
 onSelect:(s:PlayerSelection)=>void;onClose:()=>void;onPeriod:(key:string)=>void;onGroup:(g:StatGroup)=>void;
 onRetry:()=>void;onCurrentEdition:()=>void;historyHref:(playerId:string)=>string;video?:ReactNode};

const ready=<T,>(r:Resource<T>)=>r.status==='ready'?r.value:null;
const SOURCE_LABEL={protocol:'Протокол',cv:'CV',rating:'Оценка'} as const;

// Состояние блока: ошибка и отсутствие источника не скрывают остальные блоки.
function Block<T>({resource,absent,onRetry,children}:{resource:Resource<T>;absent:string;onRetry:()=>void;children:(v:T)=>ReactNode}){
 if(resource.status==='loading')return <p className="muted" role="status">Загружаем…</p>;
 if(resource.status==='absent')return <p className="muted">{absent}</p>;
 if(resource.status==='error')return <div className="block-error" role="alert"><span>{resource.message}</span><button onClick={onRetry}>Повторить</button></div>;
 return <>{children(resource.value)}</>;
}

function Readiness({model}:{model:ReportModel}){
 const p=model.protocol,c=model.cv,r=model.ratings;
 const text=(res:Resource<unknown>,ok:string,none:string)=>res.status==='ready'?ok:res.status==='absent'?none:res.status==='error'?'Ошибка загрузки':'Загружаем…';
 return <div className="readiness">
  <SourceStatus label="Протокол" detail={text(p,p.status==='ready'?`версия ${p.value.number}`:'',' ещё не опубликован')}/>
  <SourceStatus label="Видеоанализ" detail={text(c,c.status==='ready'?`${c.value.partial?'обработанный фрагмент':'весь матч'} · ${num(c.value.processed_s,0)} с`:'','ещё не опубликован')}/>
  <SourceStatus label="Оценки" detail={text(r,r.status==='ready'?`издание ${r.value.snapshot_id?.slice(0,8)}${model.context.historicalRating?' · закреплено ссылкой':''}`:'','ещё не опубликованы')}/>
 </div>;
}

function PeriodSelect({cv,value,onChange}:{cv:PublicAnalysis;value:string;onChange:(k:string)=>void}){
 const periods=cv.periods as {key:string;name:string}[];
 return <label className="period-select"><span className="sr-only">Период</span><select value={value} onChange={e=>onChange(e.target.value)}>
  {periods.map(p=><option key={p.key} value={p.key}>{periodLabel(p.key,p.name,cv.partial)}</option>)}</select></label>;
}

function Inspector({row,origin,model,match,onSelect,onClose,onCurrentEdition,historyHref}:{row:RosterRow|null;origin:PlayerSelection['origin'];
 model:ReportModel;match:PublicMatch;onSelect:(s:PlayerSelection)=>void;onClose:()=>void;onCurrentEdition:()=>void;historyHref:(id:string)=>string}){
 if(!row)return <PlayerInspector title="Игрок" onClose={onClose}><p className="muted">Этого игрока нет в опубликованных данных матча.</p></PlayerInspector>;
 const cv=ready(model.cv);const ratings=ready(model.ratings);
 const rows=ratings?.items.filter(r=>r.player_id===row.playerId)??[];
 const overall:RatingRow|undefined=ratings?.overall?.find(r=>r.player_id===row.playerId)??(rows.length===1?rows[0]:undefined);
 const side=row.side==='home'?match.home_name:row.side==='away'?match.away_name:'Команда не установлена';
 const cvPlayer=cv?.players.find(p=>p.player_id===row.playerId)??null;
 const showMap=canAttachCurrentCv({...model.context,cvRunId:cv?.run_id??null},origin)&&cvPlayer;
 const pitch=cv?.pitch as {length_m:number;width_m:number;orientation?:string}|undefined;
 const share=overall?formatFact('pass_completion_pct',overall.facts):null;
 return <PlayerInspector title={row.name} onClose={onClose}>
  <p className="inspector-meta num">{row.shirtNumber?`№ ${row.shirtNumber} · `:''}{side} · <span className="muted">источник: {SOURCE_LABEL[origin]}</span></p>
  {rows.length>0&&<p>Роль в матче: {rows.map(r=>roles[r.role as keyof typeof roles]??r.role).join(', ')}</p>}
  {overall?<section className="inspector-rating"><div><b className="rating-value num">{overall.display_rating==null?'Нет оценки':overall.display_rating.toFixed(1)}</b>
    <span className="muted small">Оценка матча · издание {ratings?.snapshot_id?.slice(0,8)}</span></div>
   {model.context.historicalRating&&<p className="small"><span className="chip">Издание закреплено ссылкой</span> <button className="btn-link" onClick={onCurrentEdition}>Открыть текущее</button></p>}
   {share&&share.text!=='Нет данных'&&<p><span className="muted">Точность передач</span><br/><b className="num">{share.text}</b>{share.note&&<span className="muted small"> · {share.note}</span>}</p>}
   {overall.reasons.length>0&&<ul className="reasons">{overall.reasons.map((r,i)=><li key={i}>{reason(r)}</li>)}</ul>}
   {typeof (overall.explanation as {text?:string}|undefined)?.text==='string'&&<p>{(overall.explanation as {text:string}).text}</p>}
  </section>:ratings?<p className="muted">Оценки этого игрока в издании нет.</p>:null}
  <section><h3>Карта времени</h3>
   {showMap&&pitch?<><PitchMap cells={cvPlayer.metrics.heatmap_s??null} lengthM={pitch.length_m} widthM={pitch.width_m} orientation={pitch.orientation??'camera'}
     maxSeconds={sharedHeatmapMax([cvPlayer.metrics.heatmap_s??null])} scaleLabel="индивидуальная шкала" label={row.name} tone={row.side??'neutral'}/>
    <p className="muted small">CV · текущая опубликованная версия · {cv?.partial?'обработанный фрагмент':'весь матч'}. Перемещения — отдельный источник, вес в оценке 0.</p></>
   :origin==='rating'?<div className="map-absent"><p>Карта этого издания недоступна</p>
     {cvPlayer&&<button className="btn-link" onClick={()=>onSelect({playerId:row.playerId,origin:'cv'})}>Открыть текущую CV-карту</button>}</div>
   :<p className="muted">Нет наблюдений этого игрока в опубликованном видеоанализе.</p>}
  </section>
  <Link className="history-link" to={historyHref(row.playerId)}>История турнира →</Link>
 </PlayerInspector>;
}

export function MatchReport({match,model,section,group,selection,onSelect,onClose,onPeriod,onGroup,onRetry,onCurrentEdition,historyHref,video}:Props){
 const roster=mergeRoster({protocol:ready(model.protocol),cv:ready(model.cv),ratings:ready(model.ratings),
  teams:{home:match.home_team_id,away:match.away_team_id}});
 const teamName=(r:{team_id?:string;side?:string|null})=>r.team_id===match.home_team_id||r.side==='home'?match.home_name
  :r.team_id===match.away_team_id||r.side==='away'?match.away_name:'—';
 const selectedRow=selection?roster.find(r=>r.playerId===selection.playerId)??null:null;
 const period=(cv:PublicAnalysis)=>model.context.periodKey||cv.primary_period_key;
 const cvValue=ready(model.cv);
 let body:ReactNode;
 if(section==='events')body=<section className="report-block"><h2>События</h2>
  <Block resource={model.protocol} absent="Протокол ещё не опубликован." onRetry={onRetry}>{p=><><PublicProtocolContent value={p}/><h3>Составы</h3><PublicLineups value={p}/>
   {match.public_protocol_id&&<Link to={`/protocols/${match.public_protocol_id}`}>Отдельная страница протокола →</Link>}</>}</Block></section>;
 else if(section==='players')body=<section className="report-block"><h2>Игроки</h2>
  {model.protocol.status!=='ready'&&<p className="muted">Официальный состав не опубликован; показаны игроки из опубликованных CV и оценок с отметкой источника.</p>}
  {roster.length?<div className="roster-columns">{(['home','away'] as const).map(side=><div key={side}><h3>{side==='home'?match.home_name:match.away_name}</h3>
   <ul className="roster-list">{roster.filter(r=>r.side===side).map(r=><li key={r.playerId} aria-selected={selection?.playerId===r.playerId}>
    <span className="num shirt">{r.shirtNumber??'—'}</span>
    <button className="link-button" onClick={()=>onSelect({playerId:r.playerId,origin:r.sources[0]})}>{r.name}</button>
    <span className="sources">{r.sources.map(s=><span key={s} className="chip">{SOURCE_LABEL[s]}</span>)}</span>
    {r.rating&&<button className="rating-chip num" onClick={()=>onSelect({playerId:r.playerId,origin:'rating'})} aria-label={`Оценка ${r.name}`}>{r.rating.display_rating?.toFixed(1)??'—'}</button>}
   </li>)}</ul></div>)}</div>:<p className="muted">Опубликованных данных об игроках пока нет.</p>}</section>;
 else if(section==='stats')body=<>
  <section className="report-block"><div className="block-head"><h2>Статистика</h2>
   {model.cv.status==='ready'&&<><PeriodSelect cv={model.cv.value} value={period(model.cv.value)} onChange={onPeriod}/>
    <span className="muted small num">CV · {num(model.cv.value.processed_s,0)} с обработано из {num(model.cv.value.video_s,0)} с записи</span></>}</div>
   <Block resource={model.cv} absent="Видеоанализ ещё не опубликован: карты и командные показатели недоступны." onRetry={onRetry}>{cv=>
    <TeamComparison cv={cv} periodKey={period(cv)} homeName={match.home_name} awayName={match.away_name}/>}</Block></section>
  <section className="report-block"><div className="group-tabs" role="group" aria-label="Группа показателей">{STAT_GROUPS.map(g=>
   <button key={g.id} aria-pressed={group===g.id} onClick={()=>onGroup(g.id)}>{g.label}</button>)}</div>
   {group==='movement'?<Block resource={model.cv} absent="Перемещения появятся после публикации видеоанализа." onRetry={onRetry}>{cv=>
     <PlayerTable group="movement" ratings={null} cv={cv} teamName={teamName} selectedId={selection?.playerId??null} onSelect={onSelect}/>}</Block>
   :<Block resource={model.ratings} absent="Показатели этой группы берутся из опубликованных оценок; издание ещё не опубликовано." onRetry={onRetry}>{r=>
     <PlayerTable group={group} ratings={r} cv={null} teamName={teamName} selectedId={selection?.playerId??null} onSelect={onSelect}/>}</Block>}
  </section></>;
 else if(section==='video')body=video;
 else body=<>
  <section className="report-block"><h2>Готовность данных</h2><Readiness model={model}/></section>
  {match.hall&&<section className="report-block venue"><h2>Площадка</h2><p className="muted">{match.hall.address} · поле {match.hall.pitch_length_m} × {match.hall.pitch_width_m} м</p><YandexMapsLink address={match.hall.address}/></section>}
  <section className="report-block"><h2>Ключевые события</h2><Block resource={model.protocol} absent="Протокол ещё не опубликован." onRetry={onRetry}>{p=>
   <PublicProtocolContent value={p} kinds={['goal','card']}/>}</Block></section>
  {cvValue&&<section className="report-block"><h2>Командные показатели · {periodLabel(period(cvValue),
   (cvValue.periods as {key:string;name:string}[]).find(p=>p.key===period(cvValue))?.name??'',cvValue.partial)}</h2>
   <TeamComparison cv={cvValue} periodKey={period(cvValue)} homeName={match.home_name} awayName={match.away_name} maps={false}/></section>}
  {model.cv.status==='error'&&<section className="report-block"><Block resource={model.cv} absent="" onRetry={onRetry}>{()=>null}</Block></section>}
  {model.ratings.status==='ready'&&<section className="report-block"><h2>Лучшие оценки</h2><ol className="leaders">{[...(model.ratings.value.overall??model.ratings.value.items)]
   .filter(r=>r.display_rating!=null).sort((a,b)=>b.display_rating!-a.display_rating!).slice(0,3).map(r=><li key={`${r.player_id}:${r.role}`}>
    <button className="link-button" onClick={()=>onSelect({playerId:r.player_id,origin:'rating'})}>{r.display_name}</button><span className="muted">{teamName(r)}</span><b className="num">{r.display_rating!.toFixed(1)}</b></li>)}</ol></section>}
  {(match.broadcast_url||match.broadcast_embed_url)&&video}
 </>;
 return <div className={`match-report${selection?' with-inspector':''}`}>
  <div className="report-main">{body}</div>
  {selection&&<Inspector row={selectedRow} origin={selection.origin} model={model} match={match} onSelect={onSelect} onClose={onClose}
   onCurrentEdition={onCurrentEdition} historyHref={historyHref}/>}
 </div>;
}
