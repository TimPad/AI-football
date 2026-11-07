import {useState} from 'react';
import {Minus,Plus} from 'lucide-react';

// Число без клавиатуры: «−» и «+» по 48 px. На границе кнопка не отключается, а сообщает предел.
export function Stepper({label,value,min,max,onChange,optional=false}:{label:string;value:number|null;min:number;max:number;onChange:(v:number|null)=>void;optional?:boolean}){
 const [note,setNote]=useState('');
 function step(d:number){
  if(value===null){if(d>0){onChange(min);setNote('')}return}
  const next=value+d;
  if(next<min){if(optional){onChange(null);setNote('')}else setNote(`Минимум ${min}`);return}
  if(next>max){setNote(`Максимум ${max}`);return}
  setNote('');onChange(next);
 }
 return <div className="stepper" role="group" aria-label={label}>
  <span className="stepper-label">{label}</span>
  <div className="stepper-controls">
   <button type="button" aria-label={`Уменьшить: ${label}`} onClick={()=>step(-1)}><Minus aria-hidden="true"/></button>
   <output aria-live="polite">{value===null?'—':value}</output>
   <button type="button" aria-label={`Увеличить: ${label}`} onClick={()=>step(1)}><Plus aria-hidden="true"/></button>
  </div>
  <span className="stepper-note" role="status">{note||(value===null&&optional?'Не задано':'')}</span>
 </div>;
}
