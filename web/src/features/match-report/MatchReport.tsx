import type {ReactNode} from 'react';
import {Link} from 'react-router-dom';
import type {MatchRatingsView,PublicMatch,PublicProtocol} from '../../api/domain';
import {PitchMap} from '../../components/pitch/PitchMap';
import {sharedHeatmapMax} from '../../components/pitch/heatmap';
import {PlayerInspector} from '../../components/match/PlayerInspector';
import {SourceStatus} from '../../components/match/SourceStatus';
import {roles,reason,num} from '../ratings/types';
import {canAttachCurrentCv,mergeRoster,type RosterRow} from './adapters';
import type {PlayerSelection,ReportModel,Resource} from './model';
import {STAT_GROUPS,formatFact,type StatGroup} from './facts';
import {PlayerTable} from './PlayerTable';
import {MatchStats,topLines} from './MatchStats';
import {MatchTimeline} from './MatchTimeline';
import {StatRow} from './StatBlocks';
import type {StatLine} from './stats';
import {CircleDot} from 'lucide-react';
import {sections} from '../../api/domain';
import './report.css';

type RatingRow=MatchRatingsView['items'][number];
type Props={match:PublicMatch;model:ReportModel;section:string;group:StatGroup|null;selection:PlayerSelection|null;
 onSelect:(s:PlayerSelection)=>void;onClose:()=>void;onPeriod:(key:string)=>void;onGroup:(g:StatGroup)=>void;
 onRetry:()=>void;onCurrentEdition:()=>void;historyHref:(playerId:string)=>string;video?:ReactNode;audience?:'public'|'cabinet';aside?:ReactNode};

const ready=<T,>(r:Resource<T>)=>r.status==='ready'?r.value:null;
const SOURCE_LABEL={protocol:'Протокол',cv:'Видео',rating:'Оценка'} as const;

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


function Inspector({row,origin,model,match,onSelect,onClose,onCurrentEdition,historyHref,audience}:{row:RosterRow|null;origin:PlayerSelection['origin'];
 model:ReportModel;match:PublicMatch;onSelect:(s:PlayerSelection)=>void;onClose:()=>void;onCurrentEdition:()=>void;historyHref:(id:string)=>string;audience:'public'|'cabinet'}){
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
    <span className="muted small">Оценка матча{audience==='cabinet'?` · издание ${ratings?.snapshot_id?.slice(0,8)}`:''}</span></div>
   {model.context.historicalRating&&<p className="small"><span className="chip">Прежняя версия рейтинга</span> <button className="btn-link" onClick={onCurrentEdition}>Открыть текущее</button></p>}
   {share&&share.text!=='Нет данных'&&<p><span className="muted">Точность передач</span><br/><b className="num">{share.text}</b>{share.note&&<span className="muted small"> · {share.note}</span>}</p>}
   {overall.reasons.length>0&&<ul className="reasons">{overall.reasons.map((r,i)=><li key={i}>{reason(r)}</li>)}</ul>}
   {typeof (overall.explanation as {text?:string}|undefined)?.text==='string'&&<p>{(overall.explanation as {text:string}).text}</p>}
  </section>:ratings?<p className="muted">Оценки этого игрока нет.</p>:null}
  <section><h3>Карта времени</h3>
   {showMap&&pitch?<><PitchMap cells={cvPlayer.metrics.heatmap_s??null} lengthM={pitch.length_m} widthM={pitch.width_m} orientation={pitch.orientation??'camera'}
     maxSeconds={sharedHeatmapMax([cvPlayer.metrics.heatmap_s??null])} scaleLabel="индивидуальная шкала" label={row.name} tone={row.side??'neutral'}/>
    <p className="muted small">По видео · {cv?.partial?'обработанный фрагмент':'весь матч'}.</p></>
   :origin==='rating'?<div className="map-absent"><p>Для этой оценки карты нет</p>
     {cvPlayer&&<button className="btn-link" onClick={()=>onSelect({playerId:row.playerId,origin:'cv'})}>Открыть карту по видео</button>}</div>
   :<p className="muted">Нет наблюдений этого игрока в опубликованном видеоанализе.</p>}
  </section>
  <Link className="history-link" to={historyHref(row.playerId)}>История турнира →</Link>
 </PlayerInspector>;
}

// В обзоре — только строки, где что-то произошло: пара нулей или прочерков ничего не говорит.
const meaningful=(l:StatLine)=>[l.home.value,l.away.value].some(v=>v!=null&&v!==0);

// Рейтинг по шкале в стиле FotMob: ≥7 зелёный, ≥6 нейтральный, ниже — оранжевый.
export const ratingTone=(v:number|null|undefined)=>v==null?'none':v>=7?'high':v>=6?'mid':'low';

type PlayerMarks={goals:number;assists:number;yellow:number;red:number};
function playerMarks(p:PublicProtocol|null):Record<string,PlayerMarks>{
 const out:Record<string,PlayerMarks>={};const get=(id:string)=>out[id]??=({goals:0,assists:0,yellow:0,red:0});
 for(const e of p?.protocol.events??[]){
  if(e.kind==='goal'){if(e.player_id&&!e.own_goal)get(e.player_id).goals++;if(e.assist_known&&e.assist_id)get(e.assist_id).assists++}
  if(e.kind==='card'&&e.player_id){if(e.card==='yellow')get(e.player_id).yellow++;else get(e.player_id).red++}
 }
 return out;
}

function Marks({m}:{m?:PlayerMarks}){
 if(!m)return null;
 return <span className="marks">{m.goals>0&&<span className="mark goal" title={`Голы: ${m.goals}`}><CircleDot aria-hidden="true"/>{m.goals>1&&m.goals}</span>}
  {m.assists>0&&<span className="mark" title={`Голевые передачи: ${m.assists}`}>А{m.assists>1&&m.assists}</span>}
  {m.yellow>0&&<i className="ev-card yellow" title="Жёлтая карточка"/>}{m.red>0&&<i className="ev-card red" title="Удаление"/>}</span>;
}

export function MatchReport({match,model,section,group:requestedGroup,selection,onSelect,onClose,onPeriod,onGroup,onRetry,onCurrentEdition,historyHref,video,audience='public',aside}:Props){
 const roster=mergeRoster({protocol:ready(model.protocol),cv:ready(model.cv),ratings:ready(model.ratings),
  teams:{home:match.home_team_id,away:match.away_team_id}});
 const teamName=(r:{team_id?:string;side?:string|null})=>r.team_id===match.home_team_id||r.side==='home'?match.home_name
  :r.team_id===match.away_team_id||r.side==='away'?match.away_name:'—';
 const selectedRow=selection?roster.find(r=>r.playerId===selection.playerId)??null:null;
 const period=model.context.periodKey||'all';
 // Без явного выбора — группа с данными: оценки есть → «Удары», иначе при видеоанализе → «Перемещения».
 const group:StatGroup=requestedGroup??(model.ratings.status!=='ready'&&model.cv.status==='ready'?'movement':'shots');
 const protocol=ready(model.protocol);const marks=playerMarks(protocol);
 const ratings=ready(model.ratings);
 const leaders=ratings?[...(ratings.overall??ratings.items)].filter(r=>r.display_rating!=null).sort((a,b)=>b.display_rating!-a.display_rating!).slice(0,3):[];
 const playersTable=<section className="report-block"><div className="block-head"><h2>Статистика игроков</h2></div>
  <div className="chips" role="group" aria-label="Группа показателей">{STAT_GROUPS.map(g=>
   <button key={g.id} aria-pressed={group===g.id} onClick={()=>onGroup(g.id)}>{g.label}</button>)}</div>
  {group==='movement'?<Block resource={model.cv} absent="Перемещения появятся после публикации видеоанализа." onRetry={onRetry}>{cv=>
    <PlayerTable group="movement" ratings={null} cv={cv} teamName={teamName} selectedId={selection?.playerId??null} onSelect={onSelect}/>}</Block>
  :<Block resource={model.ratings} absent="Показатели этой группы берутся из опубликованных оценок; издание ещё не опубликовано." onRetry={onRetry}>{r=>
    <PlayerTable group={group} ratings={r} cv={null} teamName={teamName} selectedId={selection?.playerId??null} onSelect={onSelect}/>}</Block>}
 </section>;
 let body:ReactNode;
 if(section==='events')body=<section className="report-block"><h2>События</h2>
  <Block resource={model.protocol} absent="Протокол ещё не опубликован." onRetry={onRetry}>{p=><>
   <MatchTimeline value={p}/>
   {p.protocol.public_notes&&<p className="public-note">{p.protocol.public_notes}</p>}
   <p className="muted small">Подтверждённый протокол · версия {p.number}.{p.projection.incomplete_sections.length>0&&` Заполнено не полностью: ${p.projection.incomplete_sections.map(s=>sections[s as keyof typeof sections]??s).join(', ').toLowerCase()}.`}
    {match.public_protocol_id&&<> <Link to={`/protocols/${match.public_protocol_id}`}>Полный протокол →</Link></>}</p></>}</Block></section>;
 else if(section==='players')body=<section className="report-block"><h2>Составы</h2>
  {model.protocol.status!=='ready'&&<p className="muted">Официальный состав ещё не опубликован — показаны игроки из видеоанализа и оценок.</p>}
  {roster.length?<div className="roster-columns">{(['home','away'] as const).map(side=><div key={side}><h3 className="team-title"><span className={`side-dot ${side}`}/>{side==='home'?match.home_name:match.away_name}</h3>
   <ul className="roster-list">{roster.filter(r=>r.side===side).map(r=><li key={r.playerId} aria-selected={selection?.playerId===r.playerId}>
    <span className="num shirt">{r.shirtNumber??'—'}</span>
    <button className="link-button" onClick={()=>onSelect({playerId:r.playerId,origin:r.sources[0]})}>{r.name}</button>
    <Marks m={marks[r.playerId]}/>
    {audience==='cabinet'&&<span className="sources">{r.sources.map(s=><span key={s} className="chip">{SOURCE_LABEL[s]}</span>)}</span>}
    {r.rating&&<button className={`rating-chip num tone-${ratingTone(r.rating.display_rating)}`} onClick={()=>onSelect({playerId:r.playerId,origin:'rating'})} aria-label={`Оценка ${r.name}`}>{r.rating.display_rating?.toFixed(1)??'—'}</button>}
   </li>)}</ul></div>)}</div>:<p className="muted">Опубликованных данных об игроках пока нет.</p>}</section>;
 else if(section==='stats')body=<MatchStats match={match} model={model} period={period} onPeriod={onPeriod} players={playersTable}/>;
 else if(section==='video')body=video;
 else body=<>
  {audience==='cabinet'&&<section className="report-block"><h2>Готовность данных</h2><Readiness model={model}/></section>}
  {model.protocol.status!=='absent'&&<section className="report-block"><h2>Ключевые события</h2><Block resource={model.protocol} absent="" onRetry={onRetry}>{p=>
   <MatchTimeline value={p} keyOnly/>}</Block></section>}
  {(()=>{const top=topLines(protocol,ready(model.actions),ready(model.cv),'all').filter(meaningful);return top.length>0&&<section className="report-block">
   <div className="block-head"><h2>Главное</h2>{ready(model.cv)?.partial&&<span className="muted small">видеоанализ — по обработанному фрагменту</span>}</div>
   <div className="stat-list">{top.map(l=><StatRow key={l.key} line={l}/>)}</div></section>})()}
  {model.cv.status==='error'&&<section className="report-block"><Block resource={model.cv} absent="" onRetry={onRetry}>{()=>null}</Block></section>}
  {leaders.length>0&&<section className="report-block"><h2>Лучшие игроки</h2><ol className="leaders">{leaders.map(r=><li key={`${r.player_id}:${r.role}`}>
    <button className="link-button" onClick={()=>onSelect({playerId:r.player_id,origin:'rating'})}>{r.display_name}</button><span className="muted">{teamName(r)}</span>
    <b className={`rating-chip num tone-${ratingTone(r.display_rating)}`}>{r.display_rating!.toFixed(1)}</b></li>)}</ol></section>}
  {(match.broadcast_url||match.broadcast_embed_url)&&video}
 </>;
 const inspector=selection&&<Inspector row={selectedRow} origin={selection.origin} model={model} match={match} onSelect={onSelect} onClose={onClose}
  onCurrentEdition={onCurrentEdition} historyHref={historyHref} audience={audience}/>;
 return <div className={`match-report${selection||aside?' with-aside':''}`}>
  <div className="report-main">{body}</div>
  {(inspector||aside)&&<aside className="report-aside">{inspector||aside}</aside>}
 </div>;
}
