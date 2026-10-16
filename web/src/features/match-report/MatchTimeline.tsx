import type {ReactElement} from 'react';
import {CircleDot,Target,Timer} from 'lucide-react';
import type {PublicProtocol} from '../../api/domain';

type Event=PublicProtocol['protocol']['events'][number];
type Side='home'|'away';
export type Scorer={key:string;name:string;minute:string;note:string|null};

// Минута матча по чистому времени: смещение тайма + прошедшее время, как «23'».
export function eventMinute(p:PublicProtocol,e:Event):string{
 if(e.period==null)return '—';
 if(e.elapsed_ms==null)return `${e.period}-й т.`;
 const periods=p.regulation.rules.periods_s;const offset=periods.slice(0,e.period-1).reduce((a,b)=>a+b,0);
 return `${Math.floor(offset/60)+Math.floor(e.elapsed_ms/60000)+1}'`;
}
const order=(e:Event)=>[e.period??99,e.elapsed_ms??Number.MAX_SAFE_INTEGER];
const sorted=(events:Event[])=>[...events].sort((a,b)=>{const x=order(a),y=order(b);return x[0]-y[0]||x[1]-y[1]});
const scoringSide=(e:Event):Side|null=>e.kind!=='goal'||!e.side?null:'own_goal' in e&&e.own_goal?(e.side==='home'?'away':'home'):e.side;
const playerName=(p:PublicProtocol,id:string|null|undefined)=>id?p.lineup.find(l=>l.player_id===id)?.display_name??'Игрок':null;

// Авторы голов под счётом: по стороне, получившей гол.
export function goalScorers(p:PublicProtocol):Record<Side,Scorer[]>{
 const out:Record<Side,Scorer[]>={home:[],away:[]};
 for(const e of sorted(p.protocol.events)){const side=scoringSide(e);if(!side)continue;
  const own='own_goal' in e&&e.own_goal;const pen='from_penalty' in e&&e.from_penalty;
  out[side].push({key:e.id,name:playerName(p,'player_id' in e?e.player_id:null)??'Автор не указан',minute:eventMinute(p,e),note:own?'автогол':pen?'пен.':null});}
 return out;
}

const CARD={yellow:'Жёлтая карточка',second_yellow:'Вторая жёлтая',red:'Красная карточка'} as const;
const SHOWN=new Set(['goal','card','timeout','penalty_awarded','penalty_attempt']);

function Line({p,e,score}:{p:PublicProtocol;e:Event;score:string|null}){
 const name=playerName(p,'player_id' in e?e.player_id:null);
 let icon,title,detail:string|null=name;
 if(e.kind==='goal'){icon=<CircleDot className="ev-icon goal"/>;title=`Гол${score?` · ${score}`:''}`;
  const assist='assist_id' in e&&e.assist_known?playerName(p,e.assist_id):null;
  detail=[name??'Автор не указан','own_goal' in e&&e.own_goal?'автогол':null,'from_penalty' in e&&e.from_penalty?'с пенальти':null,assist?`пас: ${assist}`:null].filter(Boolean).join(' · ');}
 else if(e.kind==='card'){const c='card' in e?e.card:'yellow';icon=<i className={`ev-card ${c==='yellow'?'yellow':'red'}`}/>;title=CARD[c as keyof typeof CARD];}
 else if(e.kind==='timeout'){icon=<Timer className="ev-icon"/>;title='Тайм-аут';detail=null;}
 else{icon=<Target className="ev-icon"/>;title=e.kind==='penalty_awarded'?'Назначен пенальти':`Пенальти: ${({goal:'гол',saved:'сейв',off_target:'мимо',unknown:'исход неизвестен'} as Record<string,string>)['outcome' in e?e.outcome:'unknown']}`;}
 const content=<span className="ev-body">{icon}<span><b>{title}</b>{detail&&<small>{detail}</small>}</span></span>;
 return <li className={`ev-row ${e.side??'none'}`}><span className="ev-side home">{e.side==='home'&&content}</span>
  <span className="ev-minute">{eventMinute(p,e)}</span><span className="ev-side away">{e.side==='away'&&content}</span></li>;
}

// Лента в две стороны по минутам, разделители таймов со счётом после тайма.
export function MatchTimeline({value:p,keyOnly=false}:{value:PublicProtocol;keyOnly?:boolean}){
 const kinds=keyOnly?new Set(['goal','card']):SHOWN;
 const events=sorted(p.protocol.events.filter(e=>kinds.has(e.kind)));
 if(!events.length)return <p className="muted">{keyOnly?'Голов и карточек в опубликованном протоколе нет.':'Событий в опубликованном протоколе нет.'}</p>;
 const score={home:0,away:0};const items:ReactElement[]=[];let period:number|null|undefined;
 for(const e of events){
  if(e.period!==period){
   if(period!==undefined)items.push(<li key={`break:${period}`} className="ev-break">{period==null?'Без времени':`Конец ${period}-го тайма`} · {score.home} : {score.away}</li>);
   period=e.period;
  }
  const side=scoringSide(e);if(side)score[side]++;
  items.push(<Line key={e.id} p={p} e={e} score={side?`${score.home} : ${score.away}`:null}/>);
 }
 return <ol className="timeline" aria-label="Лента матча">{items}</ol>;
}
