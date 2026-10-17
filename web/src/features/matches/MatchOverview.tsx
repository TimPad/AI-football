import {Link} from 'react-router-dom';
import {ArrowRight,CircleAlert,CircleCheck} from 'lucide-react';
import {api} from '../../api/client';
import type {AnalysisOverview,Match} from '../../api/domain';
import {sections} from '../../api/domain';
import {useLoad} from '../../components/ui';
import {dateTime} from './timezone';

type Row={label:string;value:string;ok:boolean;fix?:{tab:string;text:string}};
export type NextStep={title:string;hint:string;tab?:string;action?:string;done?:boolean};

// Один следующий шаг по состоянию матча: сначала подготовка и протокол, потом видеоанализ (только Админ+).
export function nextStep(m:Match,analysis:AnalysisOverview|null):NextStep{
 if(m.status==='cancelled')return {title:'Матч отменён',hint:'Ничего делать не нужно.',done:true};
 if(!m.hall_id)return {title:'Выберите зал',hint:'Зал нужен для расписания и адреса на сайте.',tab:'info',action:'К выбору зала'};
 if(!m.lineup.length)return {title:'Отметьте состав',hint:'Кто играет и под какими номерами.',tab:'lineup',action:'К составу'};
 if(m.protocol.draft){
  if(m.status==='ended')return {title:'Подтвердите протокол',hint:'Проверьте события и итог, затем подтвердите версию.',tab:'protocol',action:'К протоколу'};
  return {title:'Ведите протокол',hint:'Голы, фолы и карточки — по ходу матча.',tab:'protocol',action:'К протоколу'};
 }
 if(!m.published_version_id)return {title:'Опубликуйте протокол',hint:'Счёт, события и состав появятся на сайте.',tab:'publication',action:'К публикации'};
 if(analysis&&m.camera_profile_id){
  const confirmed=analysis.runs.some(r=>r.status==='confirmed');
  if(!analysis.runs.length)return analysis.jobs.length
   ?{title:'Загрузите результат обработки',hint:'Обработайте запись на компьютере и загрузите пакет результата.',tab:'review',action:'К видео'}
   :{title:'Начните видеоанализ',hint:'Скачайте задание, обработайте запись и загрузите результат.',tab:'review',action:'К видео'};
  if(!confirmed)return {title:'Проверьте видеоанализ',hint:'Сопоставьте игроков и подтвердите результат.',tab:'review',action:'К проверке'};
  if(!analysis.published_run_id)return {title:'Опубликуйте видеоанализ',hint:'Карты и статистика по видео появятся на сайте.',tab:'publication',action:'К публикации'};
 }
 return {title:'Матч опубликован',hint:'Зрители видят протокол'+(analysis?.published_run_id?' и видеоанализ.':'.'),done:true};
}

function NextStepCard({match:m,analytics}:{match:Match;analytics:boolean}){
 // Видеоанализ читается только для Админ+ и только когда выбрана камера.
 const needed=analytics&&!!m.camera_profile_id;
 const analysis=useLoad(async()=>needed?api<AnalysisOverview>(`/matches/${m.id}/analysis`):null,`${m.id}:${m.revision}:${needed}`);
 if(needed&&analysis.data===undefined&&!analysis.error)return <section className="surface next-step" aria-label="Следующий шаг"><p className="muted">Загружаем…</p></section>;
 const step=nextStep(m,analysis.data??null);
 return <section className={`surface next-step${step.done?' done':''}`} aria-label="Следующий шаг">
  <div>{step.done?<CircleCheck aria-hidden="true"/>:<span className="muted small">Следующий шаг</span>}<h2>{step.title}</h2><p className="muted">{step.hint}</p></div>
  {step.tab?<Link className="button primary" to={`?tab=${step.tab}`}>{step.action}<ArrowRight/></Link>
   :step.done&&m.published_version_id?<Link className="button" to={`/watch/matches/${m.id}`} target="_blank">Открыть страницу матча<ArrowRight/></Link>:null}
 </section>;
}

// Готовность из текущей сводки матча; каждая проблема ведёт к своей задаче.
export function MatchOverview({match:m,timezone,analytics}:{match:Match;timezone:string;analytics:boolean}){
 const prep:Row[]=[
  {label:'Дата и время',value:dateTime(m.scheduled_at,timezone),ok:true,fix:{tab:'info',text:'Изменить'}},
  {label:'Зал',value:m.hall_snapshot?`${m.hall_snapshot.name} · ${m.hall_snapshot.address}`:'Зал не выбран',ok:!!m.hall_id,fix:{tab:'info',text:'Выбрать зал'}},
  {label:'Состав матча',value:m.lineup.length?`${m.lineup.filter(l=>l.side==='home').length} + ${m.lineup.filter(l=>l.side==='away').length} игроков`:'Состав не отмечен',ok:m.lineup.length>0,fix:{tab:'lineup',text:'Отметить состав'}},
  {label:'Трансляция ВК',value:m.broadcast_url||m.broadcast_embed_url?'Ссылка указана':'Ссылка не указана',ok:true,fix:{tab:'info',text:'Указать'}},
  // Камера нужна только видеоанализу: её отсутствие — не проблема протокола.
  {label:'Камера для видеоанализа',value:m.camera_profile_id?'Профиль камеры выбран':'Не выбрана — нужна только для видеоанализа',ok:true,fix:{tab:'info',text:m.camera_profile_id?'Изменить':'Выбрать камеру'}},
 ];
 const incomplete=m.projection.incomplete_sections.map(s=>sections[s as keyof typeof sections]??s);
 const protocol:Row[]=[
  {label:'Версия',value:m.protocol.draft?'Черновик':'Подтверждена',ok:!m.protocol.draft,fix:{tab:'protocol',text:'Открыть протокол'}},
  {label:'На сайте',value:m.published_version_id?'Опубликована':'Не опубликована',ok:!!m.published_version_id,fix:{tab:'publication',text:'Публикация'}},
  {label:'Неполные разделы',value:incomplete.join(', ')||'Нет',ok:!incomplete.length},
 ];
 return <div className="match-overview">
  <NextStepCard match={m} analytics={analytics}/>
  <Block title="Подготовка" rows={prep}/>
  <Block title="Официальный протокол" rows={protocol}/>
 </div>;
}

function Block({title,rows}:{title:string;rows:Row[]}){
 return <section className="surface"><h2>{title}</h2><dl className="readiness-list">{rows.map(r=><div key={r.label} className={r.ok?'':'attention'}>
  <dt>{r.label}</dt><dd>{!r.ok&&<CircleAlert aria-label="Требует внимания"/>}{r.value}</dd><dd>{r.fix&&<Link to={`?tab=${r.fix.tab}`}>{r.fix.text}</Link>}</dd></div>)}</dl></section>;
}
