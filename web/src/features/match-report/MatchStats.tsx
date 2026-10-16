import type {PublicAnalysis,PublicMatch,PublicProtocol,TeamActionStats} from '../../api/domain';
import {ShotMap,type Shot} from '../../components/pitch/ShotMap';
import type {ReportModel,Resource} from './model';
import {AUTO_HINT,StatCard} from './StatBlocks';
import {TeamComparison} from './TeamComparison';
import {actionLines,cvLines,cvPeriodKey,cvThirds,protocolLines,type StatLine} from './stats';

const ready=<T,>(r:Resource<T>)=>r.status==='ready'?r.value:null;
export type PeriodOption={key:string;label:string};

// Периоды: из ручной версии действий, иначе из регламента протокола, иначе из таймов CV
// (у автоматических передач таймы видеоанализа, которые запись может и не различать).
export function periodOptions(model:ReportModel):PeriodOption[]{
 const actions=ready(model.actions);if(actions&&actions.source.kind!=='cv_auto')return actions.periods;
 const protocol=ready(model.protocol);
 if(protocol)return [{key:'all',label:'Весь матч'},...protocol.regulation.rules.periods_s.map((_,i)=>({key:String(i+1),label:`${i+1}-й тайм`}))];
 const cv=ready(model.cv);
 const halves=cv?(cv.periods as {key:string}[]).filter(p=>/^h\d$/.test(p.key)).map(p=>({key:p.key.slice(1),label:`${p.key.slice(1)}-й тайм`})):[];
 return [{key:'all',label:'Весь матч'},...halves];
}

export function PeriodChips({options,value,onChange}:{options:PeriodOption[];value:string;onChange:(key:string)=>void}){
 if(options.length<2)return null;
 return <div className="chips" role="group" aria-label="Период">{options.map(o=>
  <button key={o.key} aria-pressed={value===o.key} onClick={()=>onChange(o.key)}>{o.label}</button>)}</div>;
}

// Главные показатели — по одному из каждого доступного источника, как «Топ статистика».
export function topLines(protocol:PublicProtocol|null,actions:TeamActionStats|null,cv:PublicAnalysis|null,period:string):StatLine[]{
 const p=protocol?protocolLines(protocol,period):[];const a=actions?Object.values(actionLines(actions)).flat():[];
 const cvKey=cv?cvPeriodKey(cv,period):null;const c=cv&&cvKey?cvLines(cv,cvKey).physical:[];
 const pick=(lines:StatLine[],keys:string[])=>keys.map(k=>lines.find(l=>l.key===k)).filter((l):l is StatLine=>!!l);
 return [...pick(p,['goals']),...pick(a,['shots_total','shots_on_target','passes_accurate','saves']),...pick(p,['fouls','yellow']),...pick(c,['distance_m'])];
}

function Zones({thirds,homeName,awayName}:{thirds:Record<'home'|'away',number[]|null>;homeName:string;awayName:string}){
 const labels=['Своя треть','Средняя','Чужая треть'];
 return <div className="zones" aria-label="Доли времени по третям поля">{(['home','away'] as const).map(side=>{const v=thirds[side];
  return <div key={side} className="zone-team"><span className="zone-name"><i className={`side-dot ${side}`}/>{side==='home'?homeName:awayName}</span>
   {v?<div className="zone-bars">{v.map((share,i)=><span key={i} className={`zone ${side}`} style={{opacity:0.35+0.65*share/100}} title={`${labels[i]}: ${share} %`}>{share} %</span>)}</div>
    :<span className="muted small">Направление атаки не определено</span>}</div>})}
  <div className="zone-axis"><span>своя треть</span><span>средняя</span><span>чужая треть</span></div></div>;
}

export function MatchStats({match,model,period,onPeriod,players}:{match:PublicMatch;model:ReportModel;period:string;onPeriod:(k:string)=>void;players:React.ReactNode}){
 const protocol=ready(model.protocol),actions=ready(model.actions),cv=ready(model.cv);
 const cvKey=cv?cvPeriodKey(cv,period):null;
 const groups=actions?actionLines(actions):null;const physical=cv&&cvKey?cvLines(cv,cvKey):null;
 const thirds=cv&&cvKey?cvThirds(cv,cvKey):null;
 const lineup=protocol?.lineup??[];const name=(id:string|null)=>id?lineup.find(l=>l.player_id===id)?.display_name??null:null;
 const shots:Shot[]=actions?actions.shots.map(s=>({...s,player:name(s.player_id??null)})):[];
 const discipline=protocol?protocolLines(protocol,period).filter(l=>l.key!=='goals'):[];
 const top=topLines(protocol,actions,cv,period);
 const anything=protocol||actions||cv;
 const lines=[...top,...discipline,...(groups?Object.values(groups).flat():[])];
 const partial=lines.some(l=>l.partial),auto=lines.some(l=>l.auto);
 return <>
  <section className="report-block stats-block">
   <div className="block-head"><h2>Статистика</h2><PeriodChips options={periodOptions(model)} value={period} onChange={onPeriod}/></div>
   {!anything?<p className="muted">Статистика появится после публикации протокола, проверенных действий или видеоанализа.</p>:<div className="stat-grid">
    {actions&&actions.pitch&&<StatCard title="Карта ударов"><ShotMap shots={shots} lengthM={actions.pitch.length_m} widthM={actions.pitch.width_m}
     homeName={match.home_name} awayName={match.away_name}/></StatCard>}
    <StatCard title="Главное" lines={top}/>
    {groups&&<><StatCard title="Удары" lines={groups.shots}/><StatCard title="Передачи и ведение" lines={groups.passes}/>
     <StatCard title="Защита и единоборства" lines={groups.defense}/><StatCard title="Вратари" lines={groups.goalkeeping}/></>}
    <StatCard title="Дисциплина" lines={discipline}/>
    {physical&&<StatCard title="Физика · видеоанализ" lines={physical.physical} footer={cv!.partial?'По обработанному фрагменту записи':undefined}/>}
    {physical&&<StatCard title="Построение · видеоанализ" lines={physical.shape}>{thirds&&<Zones thirds={thirds} homeName={match.home_name} awayName={match.away_name}/>}</StatCard>}
    {cv&&cvKey&&<StatCard title="Тепловые карты" wide><TeamComparison cv={cv} periodKey={cvKey} homeName={match.home_name} awayName={match.away_name} rows={false}/></StatCard>}
    {cv&&!cvKey&&<StatCard title="Видеоанализ" wide><p className="muted">Для этого тайма видеоанализа нет: запись не разделена на таймы.</p></StatCard>}
   </div>}
   <p className="muted small stats-note">{[partial?'* — разметка категории неполная, показаны известные значения':null,
    auto?`авто — ${AUTO_HINT.charAt(0).toLowerCase()}${AUTO_HINT.slice(1)}`:null,
    actions&&actions.untimed?`Без времени и не вошли в тайм: ${actions.untimed}`:null,
    'Неизвестный исход не входит в процент'].filter(Boolean).join(' · ')}</p>
  </section>
  {players}
 </>;
}
