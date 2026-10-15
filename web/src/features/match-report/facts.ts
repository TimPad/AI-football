import type {components} from '../../api/types';
import {metrics,num,reason} from '../ratings/types';

type Fact=components['schemas']['MetricFactView'];
export type StatGroup='shots'|'passes'|'defense'|'goalkeepers'|'movement';
export const STAT_GROUPS:{id:StatGroup;label:string}[]=[{id:'shots',label:'Удары'},{id:'passes',label:'Передачи'},
 {id:'defense',label:'Защита'},{id:'goalkeepers',label:'Вратари'},{id:'movement',label:'Перемещения'}];
// Индивидуальные сохранённые факты рейтинга; командные суммы не считаются.
export const GROUP_FACTS:Record<Exclude<StatGroup,'movement'>,string[]>={
 shots:['npg_count','npg_rate10','shots_on_target_pct'],
 passes:['assists_count','assists_rate10','key_pass_rate10','pass_completion_pct','progression_rate10'],
 defense:['recoveries_count','recoveries_rate10','duel_win_pct','blocks_rate10','dangerous_turnover_rate10','discipline_cost_rate10'],
 goalkeepers:['save_pct','distribution_pct'],
};
export const MOVEMENT:{key:'observed_s'|'distance_m'|'m_per_min'|'hsr_m'|'sprints'|'vmax_ms';label:string}[]=[
 {key:'observed_s',label:'Время в видео, с'},{key:'distance_m',label:'Дистанция, м'},{key:'m_per_min',label:'Темп, м/мин'},
 {key:'hsr_m',label:'HSR, м'},{key:'sprints',label:'Спринты'},{key:'vmax_ms',label:'Макс., м/с'}];
export const factLabel=(key:string)=>metrics[key]??key;

const unresolvedKey=(key:string)=>key.replace(/_pct$/,'')+'_unresolved_count';
// «18 / 23 · 78%», при нуле возможностей — причина, а не 0%.
export function formatFact(key:string,facts:Record<string,Fact>):{text:string;note:string|null}{
 const fact=facts[key];if(!fact)return {text:'Нет данных',note:null};
 const unresolved=facts[unresolvedKey(key)]?.value;
 const note=unresolved?`Неопределённых исходов: ${num(unresolved,0)}`:null;
 if(fact.reason)return {text:reason(fact.reason),note};
 if(fact.unit==='percent')return {text:`${num(fact.numerator,0)} / ${num(fact.denominator,0)} · ${num(fact.value,0)}%`,note};
 return {text:num(fact.value),note};
}
