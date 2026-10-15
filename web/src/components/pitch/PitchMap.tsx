import {heatCellOpacity,validMatrix} from './heatmap';
import './pitch.css';

export type PitchTone='home'|'away'|'neutral';
type Props={cells:number[][]|null;lengthM:number;widthM:number;orientation:string;
 maxSeconds:number;scaleLabel:string;label?:string;tone?:PitchTone};

const format=(value:number)=>value.toLocaleString('ru-RU',{maximumFractionDigits:1});

// Разметка футзала в метрах; радиус штрафной ограничен фактической шириной зала.
function Lines({lengthM:l,widthM:w}:{lengthM:number;widthM:number}){
 const mid=w/2,goal=1.5,r=Math.max(0,Math.min(6,(w-2*goal)/2,l/4));
 const area=(x:number,dir:1|-1)=>`M${x} ${mid-goal-r}A${r} ${r} 0 0 ${dir>0?1:0} ${x+dir*r} ${mid-goal}V${mid+goal}A${r} ${r} 0 0 ${dir>0?1:0} ${x} ${mid+goal+r}`;
 return <g className="pitch-lines">
  <rect x="0" y="0" width={l} height={w}/>
  <path d={`M${l/2} 0V${w}`}/>
  <circle cx={l/2} cy={mid} r={Math.min(3,w/4)}/>
  {r>0&&<><path d={area(0,1)}/><path d={area(l,-1)}/></>}
  <path d={`M0 ${mid-goal}V${mid+goal}M${l} ${mid-goal}V${mid+goal}`} className="pitch-goal"/>
 </g>;
}

export function PitchMap({cells,lengthM,widthM,orientation,maxSeconds,scaleLabel,label='Площадка',tone='neutral'}:Props){
 const valid=validMatrix(cells);
 const observed=!!valid&&maxSeconds>0&&valid.some(row=>row.some(v=>v>0));
 const empty=!valid?'Карта недоступна':!observed?'Нет наблюдений':null;
 if(empty)return <div className="pitch-map pitch-empty"><p>{empty}</p></div>;
 const cw=lengthM/valid!.length,ch=widthM/valid![0].length;
 return <figure className={`pitch-map pitch-tone-${tone}`}>
  <svg viewBox={`0 0 ${lengthM} ${widthM}`} role="img" aria-label={`${label}: время наблюдения по ячейкам, ${scaleLabel}`}>
   <rect className="pitch-surface" x="0" y="0" width={lengthM} height={widthM}/>
   {valid!.flatMap((row,x)=>row.map((seconds,y)=>{
    const opacity=heatCellOpacity(seconds,maxSeconds);
    return opacity>0?<rect key={`${x}:${y}`} className="heat-cell" x={x*cw} y={y*ch} width={cw} height={ch} fillOpacity={opacity}>
     <title>{`${format(seconds)} с`}</title></rect>:null;
   }))}
   <Lines lengthM={lengthM} widthM={widthM}/>
  </svg>
  <figcaption>
   <span className="pitch-legend"><span className="pitch-legend-ramp" aria-hidden="true"/>{`0 — ${format(maxSeconds)} с · ${scaleLabel}`}</span>
   <span className="pitch-orientation">{orientation==='camera'?'Координаты площадки, без разворота по направлению атаки':'Ориентация не задана'}</span>
  </figcaption>
 </figure>;
}
