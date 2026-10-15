import {useState} from 'react';
import {PitchLines} from './PitchMap';
import './pitch.css';

export type Shot={id:string;side:'home'|'away';x:number;y:number;goal:boolean;on_target:boolean;blocked:boolean;outcome:string;start_ms:number|null;player:string|null};
const RESULT=(s:Shot)=>s.goal?'Гол':s.blocked?'Заблокирован':s.on_target?'В створ':s.outcome==='off_target'?'Мимо ворот':'Исход неизвестен';
const minute=(ms:number|null)=>ms==null?null:`${Math.floor(ms/60000)+1}'`;

// Точки ударов в координатах площадки из проверенных действий; без xG и без разворота по атаке.
export function ShotMap({shots,lengthM,widthM,homeName,awayName}:{shots:Shot[];lengthM:number;widthM:number;homeName:string;awayName:string}){
 const [selected,setSelected]=useState<string|null>(shots.find(s=>s.goal)?.id??shots[0]?.id??null);
 if(!shots.length)return <p className="muted">Ударов с отмеченной точкой нет.</p>;
 const current=shots.find(s=>s.id===selected)??null;
 return <figure className="shot-map pitch-map">
  <svg viewBox={`0 0 ${lengthM} ${widthM}`} role="img" aria-label={`Карта ударов: ${shots.length}`}>
   <rect className="pitch-surface" x="0" y="0" width={lengthM} height={widthM}/>
   <PitchLines lengthM={lengthM} widthM={widthM}/>
   {shots.map(s=><g key={s.id} className={`shot ${s.side}${s.goal?' goal':s.on_target?' on-target':' off-target'}${s.id===selected?' selected':''}`}
    role="button" tabIndex={0} aria-label={`${s.side==='home'?homeName:awayName}: ${RESULT(s)}${s.player?`, ${s.player}`:''}`}
    onClick={()=>setSelected(s.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSelected(s.id)}}}>
    <circle cx={s.x} cy={s.y} r={s.goal?0.75:0.55}/>{s.goal&&<circle className="goal-core" cx={s.x} cy={s.y} r={0.28}/>}
   </g>)}
  </svg>
  <figcaption>
   {current&&<span className="shot-detail"><i className={`side-dot ${current.side}`} aria-hidden="true"/>{[minute(current.start_ms),current.player??(current.side==='home'?homeName:awayName),RESULT(current)].filter(Boolean).join(' · ')}</span>}
   <span className="shot-legend"><span><i className="dot filled"/>в створ</span><span><i className="dot hollow"/>мимо или заблокирован</span><span><i className="dot goal"/>гол</span></span>
  </figcaption>
 </figure>;
}
