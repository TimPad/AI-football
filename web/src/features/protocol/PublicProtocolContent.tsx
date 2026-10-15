import type {PublicProtocol} from '../../api/domain';
import {sections} from '../../api/domain';
import {EventJournal} from './EventJournal';

export function resultNote(p:PublicProtocol):string|null{
 if(p.protocol.result_type==='technical')return `Технический результат${p.protocol.technical_reason?`: ${p.protocol.technical_reason}`:''}`;
 if(p.regulation.rules.shootout.enabled&&p.protocol.shootout_totals.home!=null)return `Серия пенальти ${p.protocol.shootout_totals.home} : ${p.protocol.shootout_totals.away??'—'}`;
 return null;
}

// Официальный журнал опубликованной версии; только public DTO.
export function PublicProtocolContent({value:p,kinds}:{value:PublicProtocol;kinds?:string[]}){
 const events=kinds?p.protocol.events.filter(e=>kinds.includes(e.kind)):p.protocol.events;
 return <>
  <p className="muted">Подтверждённый протокол · версия {p.number}. Известные голы: {p.projection.event_score.home} : {p.projection.event_score.away}. Основное время: {p.regulation.total_s/60} минут.</p>
  {p.regulation.rules.shootout.enabled&&<p>Серия пенальти: {p.protocol.shootout_totals.home??'—'} : {p.protocol.shootout_totals.away??'—'} (известные попытки с голом: {p.projection.shootout_score.home} : {p.projection.shootout_score.away})</p>}
  {p.protocol.result_type==='technical'&&<p>Технический результат: {p.protocol.technical_reason}</p>}
  <p>Не полностью заполнено: {p.projection.incomplete_sections.map(s=>sections[s as keyof typeof sections]??s).join(', ')||'нет пропусков'}</p>
  {events.length?<EventJournal events={events} lineup={p.lineup} home={p.home_name} away={p.away_name}/>:<p className="muted">Событий этого типа в протоколе нет.</p>}
  {!kinds&&p.protocol.public_notes&&<p>{p.protocol.public_notes}</p>}
  {!kinds&&<p className="muted">Подтверждён: {new Date(p.confirmed_at).toLocaleString('ru-RU')}. Опубликован: {new Date(p.published_at).toLocaleString('ru-RU')}.</p>}
 </>;
}

export function PublicLineups({value:p}:{value:PublicProtocol}){
 return <div className="lineups">{(['home','away'] as const).map(side=><div key={side}><h3>{side==='home'?p.home_name:p.away_name}</h3>
  <p>{p.lineup.filter(l=>l.side===side).map(l=>`${l.shirt_number??'—'} · ${l.display_name}`).join(', ')||'Состав не указан'}</p></div>)}</div>;
}
