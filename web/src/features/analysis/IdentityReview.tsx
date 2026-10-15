import {useState,useEffect} from 'react';
import type {AnalysisRun,AnalysisAssignment} from '../../api/domain';
import type {IdentitySuggestion} from './understandingTypes';
import {useDraft} from '../protocol/drafts';
import {ErrorBox,downloadJson} from '../../components/ui';
import {TRACK_FILTERS,filteredCount,trackState,visibleTrackIds,type TrackFilter} from './reviewQueue';
import './review.css';
type Review={side_map:AnalysisRun['side_map'],assignments:AnalysisAssignment[]};
function valid(v:unknown):v is Review{if(!v||typeof v!=='object')return false;const r=v as Review;return !!r.side_map&&['home','away'].includes(r.side_map.A)&&['home','away'].includes(r.side_map.B)&&Array.isArray(r.assignments)&&r.assignments.every(a=>Number.isInteger(a.track_id)&&(a.player_id==null||typeof a.player_id==='string')&&(a.excluded_reason==null||typeof a.excluded_reason==='string'))}
type View={filter?:TrackFilter;page:number;item:number|null};
const PAGE=20;
export function IdentityReview({run,actorId,editable,onSave,onDirty,suggestions=[],onEvidence,view:external,onView}:{run:AnalysisRun,actorId:string,editable:boolean,onSave:(v:Review)=>Promise<unknown>,onDirty?:(dirty:boolean)=>void,suggestions?:IdentitySuggestion[],onEvidence?:(ids:string[])=>void,view?:View,onView?:(patch:Partial<View>)=>void}){
 const draft=useDraft<Review>(`aifootball:identity:v1:${actorId}:${run.id}`,{side_map:run.side_map,assignments:run.assignments},valid);const [error,setError]=useState<unknown>();const [busy,setBusy]=useState(false);
 const [local,setLocal]=useState<View>({page:1,item:null});const view=external??local;const navigate=onView??((patch:Partial<View>)=>setLocal(v=>({...v,...patch})));
 const [queueOpen,setQueueOpen]=useState(false);
 useEffect(()=>{onDirty?.(draft.dirty)},[draft.dirty,onDirty]);
 function change(next:Review){draft.change(next);onDirty?.(true)}
 function assign(track_id:number,value:string){const rest=draft.value.assignments.filter(a=>a.track_id!==track_id);const old=draft.value.assignments.find(a=>a.track_id===track_id);change({...draft.value,assignments:value?[...rest,value==='exclude'?{track_id,excluded_reason:old?.excluded_reason??''}:{track_id,player_id:value}]:rest})}
 function reason(track_id:number,value:string){change({...draft.value,assignments:draft.value.assignments.map(a=>a.track_id===track_id?{...a,excluded_reason:value}:a)})}
 // Сохраняется весь черновик, включая строки вне текущего фильтра и страницы.
 async function save(){setBusy(true);setError(undefined);try{await onSave(draft.value);draft.markSaved(draft.value);onDirty?.(false)}catch(e){setError(e)}finally{setBusy(false)}}
 const sidesChanged=JSON.stringify(draft.value.side_map)!==JSON.stringify(run.side_map);
 const disabled=!editable||busy||draft.corrupt;
 const assignments=draft.value.assignments;
 const filter:TrackFilter=view.filter??(filteredCount(run,'unassigned',assignments)?'unassigned':'all');
 const total=filteredCount(run,filter,assignments);const pages=Math.max(1,Math.ceil(total/PAGE));const page=Math.min(view.page,pages);
 const visible=visibleTrackIds(run,filter,page,PAGE,assignments);
 const selectedId=view.item!=null&&run.tracks.some(t=>t.track_id===view.item)?view.item:visible[0]??run.tracks[0]?.track_id??null;
 const t=run.tracks.find(x=>x.track_id===selectedId)??null;
 const a=t?assignments.find(x=>x.track_id===t.track_id):undefined;const side=t?.team?draft.value.side_map[t.team]:null;
 const hint=t?suggestions.find(h=>h.track_id===t.track_id):undefined;
 const decision=a?.player_id?'player':a?.excluded_reason!=null?'exclude':'unknown';
 const next=()=>{const order=visible.length?visible:run.tracks.map(x=>x.track_id);const i=order.indexOf(selectedId??-1);const following=order.find((id,k)=>k>i&&id!==selectedId);navigate({item:following??order[0]??null})};
 const thumb=(id:number,has:boolean,cls='')=>has?<img className={`track-thumb ${cls}`} src={`/api/v1/matches/${run.match_id}/analysis/runs/${run.id}/thumbs/${id}`} alt={`Фрагмент ${id}`}/>:<span className={`thumb-missing ${cls}`}>Кадр недоступен</span>;
 const dirtyCount=draft.dirty?draft.value.assignments.length:0;
 return <section className="identity-review" aria-label="Сопоставление игроков">
  <div className="review-bar"><div className="form-grid side-map">{(['A','B'] as const).map(s=><label className="field" key={s}><span>Команда {s} на видео</span><select aria-label={`Команда ${s} на видео`} value={draft.value.side_map[s]} disabled={disabled} onChange={e=>change({...draft.value,side_map:{A:e.target.value as 'home'|'away',B:e.target.value==='home'?'away':'home',...(s==='B'?{B:e.target.value as 'home'|'away',A:e.target.value==='home'?'away':'home'}:{})}})}><option value="home">{run.context.teams.home.name}</option><option value="away">{run.context.teams.away.name}</option></select></label>)}</div>
   <label className="field"><span>Показать треки</span><select aria-label="Фильтр треков" value={filter} onChange={e=>navigate({filter:e.target.value as TrackFilter,page:1})}>{TRACK_FILTERS.map(f=><option key={f.id} value={f.id}>{f.label} · {filteredCount(run,f.id,assignments)}</option>)}</select></label>
   <button className="queue-toggle" aria-expanded={queueOpen} onClick={()=>setQueueOpen(!queueOpen)}>Очередь · {total}</button></div>
  <div className={`review-panes${queueOpen?' queue-open':''}`}>
   <nav className="surface review-queue" aria-label="Очередь треков"><div className="queue-head"><h3>Треки</h3><span className="muted small num">{total?`${(page-1)*PAGE+1}–${(page-1)*PAGE+visible.length} из ${total}`:'0'}</span></div>
    {visible.length?<ul>{visible.map(id=>{const track=run.tracks.find(x=>x.track_id===id)!;const st=trackState(assignments,id);const saved=trackState(run.assignments,id);
     return <li key={id}><button aria-current={id===selectedId?'true':undefined} onClick={()=>{navigate({item:id});setQueueOpen(false)}}>{thumb(id,!!track.thumb,'small')}<span><b>Трек {id}</b><small className="num">{track.intervals[0]?`${track.intervals[0][0].toFixed(1)}–${track.intervals[track.intervals.length-1][1].toFixed(1)} с`:'интервал неизвестен'}</small>
      <small className={st!==saved?'changed':''}>{st==='assigned'?'Назначен':st==='excluded'?'Исключён':'Не назначен'}{st!==saved?' · не сохранено':''}</small></span></button></li>})}</ul>
    :<p className="muted small">Треков с таким условием нет.</p>}
    {pages>1&&<div className="pager"><button aria-label="Предыдущая страница" disabled={page<=1} onClick={()=>navigate({page:page-1})}>‹</button><span className="muted small num">Страница {page} из {pages}</span><button aria-label="Следующая страница" disabled={page>=pages} onClick={()=>navigate({page:page+1})}>›</button></div>}
   </nav>
   <article className="surface review-material" aria-label="Материал трека">{t?<>
    <div className="material-head"><h2>Трек {t.track_id}</h2><span className="muted small">{t.team?`Команда ${t.team} на видео`:'Команда не определена'} · {t.role}</span></div>
    {thumb(t.track_id,!!t.thumb,'large')}
    {!t.thumb&&<p className="muted small">Кадр не приложен к результату. Проверьте трек по интервалам записи и составу.</p>}
    <h3>Интервалы в записи</h3><p className="intervals num">{t.intervals.map(([start,end],i)=><span key={i}>{start.toFixed(1)}–{end.toFixed(1)} с</span>)}</p>
    {!t.has_metrics&&<p className="muted small">Короткий фрагмент · метрик нет</p>}
    {hint&&<div className="identity-hint">{sidesChanged?<small>Сохраните стороны для обновления подсказок.</small>:<><b>{hint.status==='conflict'?'Конфликт номера':'Предположение'}: №{hint.number??'?'}{hint.player_id?` · ${run.context.rosters.find(p=>p.player_id===hint.player_id)?.display_name??'Игрок состава'}`:''}</b><small>Подсказка, требует проверки — игрок не назначается автоматически.</small>{hint.reasons.map((r,i)=><small key={i}>{r}</small>)}</>}{hint.evidence_ids.length>0&&onEvidence&&<button onClick={()=>onEvidence(hint.evidence_ids)}>Кадры номера #{t.track_id}</button>}</div>}
   </>:<p className="muted">Треков в этой версии нет.</p>}</article>
   <aside className="surface review-inspector" aria-label="Назначение трека">{t?<>
    <h3>Назначение трека {t.track_id}</h3>
    <div className="decision" role="radiogroup" aria-label="Решение по треку">
     {([['player','Игрок из заявки','Назначить постоянную личность'],['unknown','Неизвестный участник','Личность не установлена'],['exclude','Исключить трек','Не игрок: судья, зритель, ошибка']] as const).map(([key,label,hintText])=>
      <label key={key}><input type="radio" name={`decision-${t.track_id}`} checked={decision===key} disabled={disabled} onChange={()=>assign(t.track_id,key==='player'?(a?.player_id??run.context.rosters.find(p=>!side||p.side===side)?.player_id??''):key==='exclude'?'exclude':'')}/><span><b>{label}</b><small>{hintText}</small></span></label>)}
    </div>
    <label className="field"><span>Игрок</span><select aria-label={`Игрок фрагмента ${t.track_id}`} value={a?.player_id??(a?.excluded_reason!=null?'exclude':'')} disabled={disabled} onChange={e=>assign(t.track_id,e.target.value)}><option value="">Не определён</option>{run.context.rosters.filter(p=>!side||p.side===side).map(p=><option key={p.player_id} value={p.player_id}>{p.shirt_number??'—'} · {p.display_name}</option>)}<option value="exclude">Исключить фрагмент</option></select></label>
    {a?.excluded_reason!=null&&<label className="field"><span>Причина исключения</span><input aria-label={`Причина исключения ${t.track_id}`} value={a.excluded_reason} disabled={disabled} maxLength={500} placeholder="Причина исключения" onChange={e=>reason(t.track_id,e.target.value)}/></label>}
    <details><summary>Источник</summary><dl className="small num"><dt>Версия</dt><dd>{String(run.id).slice(0,8)} · ревизия {run.revision}</dd><dt>Задание</dt><dd>{run.job_id?String(run.job_id).slice(0,8):"—"}</dd><dt>UUID игрока</dt><dd>{a?.player_id??'—'}</dd></dl></details>
    <button onClick={next}>Следующий трек</button>
   </>:null}</aside>
  </div>
  {draft.dirty&&<p className="draft-banner">Черновик сопоставления сохранён в этом браузере{dirtyCount?` · назначений в черновике: ${dirtyCount}`:''}. Подтверждение версии недоступно до сохранения.</p>}
  <p className="muted small">Несколько треков можно назначить одному игроку. Пересекающиеся по времени треки нужно проверить. Неопределённые треки не попадают в индивидуальную статистику.</p>
  <ErrorBox error={error||draft.error}/>{editable&&<div className="row"><button className="primary" disabled={disabled} onClick={save}>Сохранить сопоставление</button><button onClick={()=>downloadJson(draft.raw??draft.value,'сопоставление.json')}>Скачать черновик</button>{draft.corrupt&&<button onClick={draft.clear}>Очистить повреждённый черновик</button>}</div>}
 </section>;
}
