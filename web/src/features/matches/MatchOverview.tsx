import {Link} from 'react-router-dom';
import {CircleAlert} from 'lucide-react';
import type {Match} from '../../api/domain';
import {sections} from '../../api/domain';
import {dateTime} from './timezone';

type Row={label:string;value:string;ok:boolean;fix?:{tab:string;text:string}};

// Готовность из текущей сводки матча; каждая проблема ведёт к своей задаче.
export function MatchOverview({match:m,timezone,analytics}:{match:Match;timezone:string;analytics:boolean}){
 const prep:Row[]=[
  {label:'Дата и время',value:dateTime(m.scheduled_at,timezone),ok:true,fix:{tab:'info',text:'Изменить'}},
  {label:'Зал',value:m.hall_snapshot?`${m.hall_snapshot.name} · ${m.hall_snapshot.address}`:'Зал не выбран',ok:!!m.hall_id,fix:{tab:'info',text:'Выбрать зал'}},
  {label:'Состав матча',value:m.lineup.length?`${m.lineup.filter(l=>l.side==='home').length} + ${m.lineup.filter(l=>l.side==='away').length} игроков`:'Состав не отмечен',ok:m.lineup.length>0,fix:{tab:'lineup',text:'Отметить состав'}},
  {label:'Трансляция ВК',value:m.broadcast_url||m.broadcast_embed_url?'Ссылка указана':'Ссылка не указана',ok:true,fix:{tab:'info',text:'Указать'}},
  {label:'Камера для видеоанализа',value:m.camera_profile_id?'Профиль камеры выбран':'Не выбрана: нужна только для CV, протокол можно вести',ok:!!m.camera_profile_id,fix:{tab:'info',text:'Выбрать камеру'}},
 ];
 const incomplete=m.projection.incomplete_sections.map(s=>sections[s as keyof typeof sections]??s);
 const protocol:Row[]=[
  {label:'Версия',value:m.protocol.draft?'Черновик':'Подтверждена',ok:!m.protocol.draft,fix:{tab:'protocol',text:'Открыть протокол'}},
  {label:'На сайте',value:m.published_version_id?'Опубликована':'Не опубликована',ok:!!m.published_version_id,fix:{tab:'publication',text:'Публикация'}},
  {label:'Неполные разделы',value:incomplete.join(', ')||'Нет',ok:!incomplete.length},
 ];
 return <div className="match-overview">
  <Block title="Подготовка" rows={prep}/>
  <Block title="Официальный протокол" rows={protocol}/>
  <section className="surface"><h2>Следующие задачи</h2><ul className="task-links">
   <li><Link to="?tab=review">Проверка записи</Link><span className="muted">Импорт результата и сопоставление игроков</span></li>
   {analytics&&<li><Link to="?tab=participation">Участие</Link><span className="muted">Время на площадке и роли</span></li>}
   {analytics&&<li><Link to="?tab=actions">Действия</Link><span className="muted">Проверенные действия и полнота</span></li>}
   <li><Link to="?tab=report">Отчёт</Link><span className="muted">Чтение данных матча в кабинете</span></li>
   <li><Link to="?tab=publication">Публикация</Link><span className="muted">Независимые публикации источников</span></li>
  </ul></section>
 </div>;
}

function Block({title,rows}:{title:string;rows:Row[]}){
 return <section className="surface"><h2>{title}</h2><dl className="readiness-list">{rows.map(r=><div key={r.label} className={r.ok?'':'attention'}>
  <dt>{r.label}</dt><dd>{!r.ok&&<CircleAlert aria-label="Требует внимания"/>}{r.value}</dd><dd>{r.fix&&<Link to={`?tab=${r.fix.tab}`}>{r.fix.text}</Link>}</dd></div>)}</dl></section>;
}
