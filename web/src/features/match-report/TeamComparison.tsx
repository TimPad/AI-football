import type {PublicAnalysis} from '../../api/domain';
import {PitchMap} from '../../components/pitch/PitchMap';
import {sharedHeatmapMax} from '../../components/pitch/heatmap';
import {num} from '../ratings/types';

type TeamValues={distance_m?:number|null;observed_s?:number|null;m_per_min?:number|null;hsr_m?:number|null;sprints?:number|null;
 heatmap_s?:number[][]|null;width_m?:number|null;depth_m?:number|null;compactness_m2?:number|null;metric_notes?:Record<string,string>};
type Period=PublicAnalysis['periods'][number]&{key:string;name:string;teams?:Record<string,TeamValues>};
const ROWS:{key:keyof TeamValues;label:string;unit:string}[]=[{key:'distance_m',label:'Дистанция',unit:'м'},{key:'m_per_min',label:'Темп движения',unit:'м/мин'},
 {key:'hsr_m',label:'HSR',unit:'м'},{key:'sprints',label:'Спринты',unit:''},{key:'width_m',label:'Ширина команды',unit:'м'},
 {key:'depth_m',label:'Глубина команды',unit:'м'},{key:'compactness_m2',label:'Компактность',unit:'м²'}];

// Команды по side_map: A/B → home/away. Числа только из сохранённого отчёта периода.
export function teamsBySide(cv:PublicAnalysis,periodKey:string){
 const period=(cv.periods as Period[]).find(p=>p.key===periodKey);
 const out:{home:TeamValues|null;away:TeamValues|null}={home:null,away:null};
 for(const [code,values] of Object.entries(period?.teams??{})){const side=cv.side_map[code];if(side)out[side]=values}
 return {period,...out};
}

export function TeamComparison({cv,periodKey,homeName,awayName,maps=true}:{cv:PublicAnalysis;periodKey:string;homeName:string;awayName:string;maps?:boolean}){
 const {period,home,away}=teamsBySide(cv,periodKey);
 if(!period)return <p className="muted">Период недоступен.</p>;
 const max=sharedHeatmapMax([home?.heatmap_s??null,away?.heatmap_s??null]);
 const pitch=cv.pitch as {length_m:number;width_m:number;orientation?:string};
 return <div className="team-comparison">
  {maps&&<div className="team-maps">{([['home',homeName,home],['away',awayName,away]] as const).map(([side,name,values])=>
   <div key={side}><h3 className="team-title"><span className={`side-dot ${side}`}/>{name}</h3>
    <PitchMap cells={values?.heatmap_s??null} lengthM={pitch.length_m} widthM={pitch.width_m} orientation={pitch.orientation??'camera'}
     maxSeconds={max} scaleLabel="общая шкала обеих команд, суммарное время игроков" label={name} tone={side}/></div>)}</div>}
  <table className="compare-table"><caption className="sr-only">Командные показатели периода</caption><tbody>{ROWS.map(row=>{
   const h=home?.[row.key] as number|null|undefined,a=away?.[row.key] as number|null|undefined;
   const top=Math.max(h??0,a??0);
   return <tr key={row.key}><td className="num home">{h==null?'—':`${num(h)} ${row.unit}`}</td>
    <td><span className="bar home"><i style={{width:top&&h!=null?`${100*h/top}%`:0}}/></span></td>
    <th scope="row">{row.label}</th>
    <td><span className="bar away"><i style={{width:top&&a!=null?`${100*a/top}%`:0}}/></span></td>
    <td className="num away">{a==null?'—':`${num(a)} ${row.unit}`}</td></tr>;})}</tbody></table>
 </div>;
}
