import {PitchMap,type PitchTone} from '../../components/pitch/PitchMap';
import {useState} from 'react';
import {Link} from 'react-router-dom';
import type {components} from '../../api/types';
type Metrics=components['schemas']['PublicMetrics']|components['schemas']['MetricValues'];
type Person={player_id:string,display_name:string,shirt_number?:string|null,side:string,metrics:Metrics};
export const measure=(value:number|null|undefined,digits=1)=>value==null?'—':value.toLocaleString('ru-RU',{maximumFractionDigits:digits});
// Старые экраны используют общую карту площадки; клетка отчёта — 1 м, собственная шкала.
export function Heatmap({values,tone='neutral'}:{values:number[][];tone?:PitchTone}){
 const max=Math.max(0,...values.flat().filter(Number.isFinite));
 return <PitchMap cells={values} lengthM={values.length} widthM={values[0]?.length??0} orientation="camera" maxSeconds={max}
  scaleLabel="собственная шкала карты" tone={tone}/>;
}

export function AnalysisReport({players,partial=false,linkPlayers=true,videoSeconds,processedSeconds,heading='Статистика по видео'}:{heading?:string,players:Person[],partial?:boolean,linkPlayers?:boolean,videoSeconds?:number,processedSeconds?:number}){
 const [selected,setSelected]=useState<string>();const person=players.find(p=>p.player_id===selected)??players[0];
 return <section className="surface analysis-report"><div className="panel-head"><h2>{heading}</h2>{partial&&<span className="analysis-partial">Частичная запись</span>}</div><p className="muted">Время в анализируемом видео{videoSeconds!=null&&` · запись ${measure(videoSeconds)} с, обработано ${measure(processedSeconds)} с`}. Показатели относятся к видимым фрагментам и основному периоду; пропуски записи не заполняются.</p>{!players.length?<p>Подтверждённых игроков пока нет.</p>:<><div className="table-scroll"><table><thead><tr><th>Игрок</th><th>Время в анализируемом видео</th><th>Дистанция, м</th><th>м/мин</th><th>HSR, м</th><th>Спринты</th><th>Макс., м/с</th><th>Карта</th></tr></thead><tbody>{players.map(p=><tr key={p.player_id}><td>{linkPlayers?<Link to={`/players/${p.player_id}/analysis`}>{p.shirt_number??'—'} · {p.display_name}</Link>:`${p.shirt_number??'—'} · ${p.display_name}`}</td>{(['observed_s','distance_m','m_per_min','hsr_m','sprints','vmax_ms'] as const).map(k=><td key={k} title={'metric_notes' in p.metrics?p.metrics.metric_notes?.[k]:undefined}>{measure(p.metrics[k])}</td>)}<td><button onClick={()=>setSelected(p.player_id)} aria-label={`Карта ${p.display_name}`}>Показать</button></td></tr>)}</tbody></table></div><p className="muted"><span>Нет данных</span>: «—». HSR — дистанция с высокой скоростью; оценка зависит от качества калибровки и трекинга.</p>{person&&<div className="analysis-map"><h3>{person.display_name} · тепловая карта</h3>{person.metrics.heatmap_s?<Heatmap values={person.metrics.heatmap_s}/>:<p className="muted">Тепловая карта недоступна.</p>}</div>}</>}</section>;
}
