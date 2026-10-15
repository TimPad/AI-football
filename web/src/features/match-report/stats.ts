import type {PublicAnalysis,PublicProtocol,TeamActionStats} from '../../api/domain';
import {num} from '../ratings/types';
import {teamsBySide} from './TeamComparison';

export type Side='home'|'away';
export type Cell={value:number|null;text:string;note?:string};
export type StatSource='protocol'|'actions'|'cv';
export type StatLine={key:string;label:string;home:Cell;away:Cell;better:'higher'|'lower'|'none';source:StatSource;partial?:boolean};
export type ActionGroup='shots'|'passes'|'defense'|'goalkeeping';

const SIDES:Side[]=['home','away'];
const empty:Cell={value:null,text:'—'};
const count=(value:number|null|undefined):Cell=>value==null?empty:{value,text:num(value,0)};

// Значение лидера выделяется только при двух известных и разных числах.
export function leader(line:StatLine):Side|null{
 const h=line.home.value,a=line.away.value;
 if(line.better==='none'||h==null||a==null||h===a)return null;
 return (line.better==='higher')===(h>a)?'home':'away';
}

// Период отчёта: 'all' или номер тайма; у CV свои ключи (h1/h2), у действий — номер.
export function cvPeriodKey(cv:PublicAnalysis,period:string):string|null{
 const keys=(cv.periods as {key:string}[]).map(p=>p.key);
 if(period==='all')return cv.primary_period_key;
 const key=`h${period}`;return keys.includes(key)?key:null;
}

type Event=PublicProtocol['protocol']['events'][number];
const inPeriod=(e:Event,period:string)=>period==='all'||String(e.period)===period;

// Протокол: при выборе периода считаются события с этим периодом; итог матча — из сохранённой проекции.
export function protocolLines(p:PublicProtocol,period:string):StatLine[]{
 const events=p.protocol.events.filter(e=>inPeriod(e,period));
 const completeness=p.protocol.completeness as Record<string,string>;
 const by=(kind:string,side:Side,test:(e:Event)=>boolean=()=>true)=>events.filter(e=>e.kind===kind&&e.side===side&&test(e)).length;
 const card=(e:Event)=>'card' in e?e.card:null;
 const total=(key:'fouls'|'yellow_cards'|'dismissals',side:Side,section:string,fallback:number):Cell=>{
  const official=period==='all'?(p.projection.effective_totals as Record<Side,Record<string,number|null>>)[side][key]??null:null;
  if(official!=null)return count(official);
  return completeness[section]==='complete'?count(fallback):{...count(fallback),note:'известные'};
 };
 const goals=(side:Side)=>{
  if(period==='all')return count(p.projection.effective_score[side]??null);
  const scores=(p.projection.period_event_scores as Record<string,Record<Side,number>>)[period];
  return count(scores?.[side]??0);
 };
 const lines:StatLine[]=[
  {key:'goals',label:'Голы',home:goals('home'),away:goals('away'),better:'higher',source:'protocol',partial:completeness.goals!=='complete'},
  {key:'fouls',label:'Фолы',home:total('fouls','home','fouls',by('foul','home')),away:total('fouls','away','fouls',by('foul','away')),better:'lower',source:'protocol',partial:completeness.fouls!=='complete'},
 ];
 if(period!=='all'){
  const acc=p.projection.accumulated_fouls as Record<Side,Record<string,number>>;
  if(SIDES.some(s=>acc[s]?.[period]!=null))lines.push({key:'accumulated',label:'Накопленные фолы',home:count(acc.home?.[period]??0),away:count(acc.away?.[period]??0),better:'lower',source:'protocol'});
 }
 lines.push(
  {key:'yellow',label:'Жёлтые карточки',home:total('yellow_cards','home','cards',by('card','home',e=>card(e)==='yellow'||card(e)==='second_yellow')),
   away:total('yellow_cards','away','cards',by('card','away',e=>card(e)==='yellow'||card(e)==='second_yellow')),better:'lower',source:'protocol',partial:completeness.cards!=='complete'},
  {key:'dismissals',label:'Удаления',home:total('dismissals','home','cards',by('card','home',e=>card(e)==='red'||card(e)==='second_yellow')),
   away:total('dismissals','away','cards',by('card','away',e=>card(e)==='red'||card(e)==='second_yellow')),better:'lower',source:'protocol',partial:completeness.cards!=='complete'});
 const timeouts=SIDES.map(s=>by('timeout',s));
 if(timeouts.some(Boolean))lines.push({key:'timeouts',label:'Тайм-ауты',home:count(timeouts[0]),away:count(timeouts[1]),better:'none',source:'protocol'});
 const penalties=SIDES.map(s=>by('penalty_awarded',s));
 if(penalties.some(Boolean))lines.push({key:'penalties',label:'Назначено пенальти',home:count(penalties[0]),away:count(penalties[1]),better:'higher',source:'protocol'});
 return lines;
}

type Row=TeamActionStats['rows'][number];
const LOWER=new Set(['turnovers','errors']);
function actionCell(row:Row,side:Side):Cell{
 const v=row[side];
 if(row.unit==='percent'){
  if(!v.denominator)return {value:null,text:'—',note:v.unknown?`исход неизвестен: ${v.unknown}`:undefined};
  return {value:v.value,text:`${v.numerator}/${v.denominator} (${num(v.value,0)} %)`,note:v.unknown?`ещё неизвестно: ${v.unknown}`:undefined};
 }
 return count(v.value);
}

export function actionLines(stats:TeamActionStats):Record<ActionGroup,StatLine[]>{
 const out:Record<ActionGroup,StatLine[]>={shots:[],passes:[],defense:[],goalkeeping:[]};
 for(const row of stats.rows)out[row.group].push({key:row.key,label:row.label,home:actionCell(row,'home'),away:actionCell(row,'away'),
  better:LOWER.has(row.key)?'lower':row.key==='shots_off_target'||row.key==='shots_blocked'?'none':'higher',source:'actions',partial:row.coverage!=='complete'});
 return out;
}

type TeamValues=NonNullable<ReturnType<typeof teamsBySide>['home']>;
const cvCell=(v:number|null|undefined,unit:string,digits=1):Cell=>v==null?empty:{value:v,text:`${num(v,digits)}${unit?` ${unit}`:''}`};

export function cvLines(cv:PublicAnalysis,periodKey:string):{physical:StatLine[];shape:StatLine[]}{
 const {home,away}=teamsBySide(cv,periodKey);
 const line=(key:keyof TeamValues,label:string,unit:string,better:StatLine['better'],digits=1):StatLine=>({key:String(key),label,
  home:cvCell(home?.[key] as number|null|undefined,unit,digits),away:cvCell(away?.[key] as number|null|undefined,unit,digits),better,source:'cv'});
 return {
  physical:[line('distance_m','Дистанция','м','higher'),line('m_per_min','Темп движения','м/мин','higher'),line('hsr_m','Высокоинтенсивный бег (HSR)','м','higher'),
   line('sprints','Спринты','','higher',0)],
  shape:[line('width_m','Ширина команды','м','none'),line('depth_m','Глубина команды','м','none'),line('compactness_m2','Компактность','м²','none')],
 };
}

// Трети: свои / средняя / чужая, в процентах времени центра команды.
export function cvThirds(cv:PublicAnalysis,periodKey:string):Record<Side,number[]|null>|null{
 const period=(cv.periods as {key:string;thirds?:Record<string,number[]|null>}[]).find(p=>p.key===periodKey);
 if(!period?.thirds)return null;
 const out:Record<Side,number[]|null>={home:null,away:null};
 for(const [code,v] of Object.entries(period.thirds)){const side=cv.side_map[code];if(side)out[side]=v}
 return out.home||out.away?out:null;
}
