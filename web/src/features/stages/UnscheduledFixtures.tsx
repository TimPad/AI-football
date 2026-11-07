import type {FixtureView} from './api';
import './stages.css';

// Пары без даты по турам и раундам. В кабинете — кнопка «Назначить», у зрителя — только список.
export function UnscheduledFixtures({items,title,onSchedule}:{items:FixtureView[];title:string;onSchedule?:(f:FixtureView)=>void}){
 if(!items.length)return null;
 const groups=new Map<string,FixtureView[]>();
 for(const f of items){const key=`${f.stage_name} · ${f.label}`;groups.set(key,[...(groups.get(key)??[]),f])}
 return <section className="unscheduled surface" aria-label={title}><h2>{title}</h2>
  {[...groups].map(([label,list])=><div key={label}><h3>{label}</h3>{list.map(f=><div className="unscheduled-row" key={f.id}>
   <span>{f.home.label} — {f.away.label}</span>
   {onSchedule&&(f.can_schedule?<button type="button" onClick={()=>onSchedule(f)}>Назначить</button>:<span className="muted small">Соперник ещё не известен</span>)}</div>)}</div>)}
 </section>;
}
