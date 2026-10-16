import type {ReactNode} from 'react';
import {leader,type StatLine} from './stats';

export const AUTO_HINT='Автоматически по видео: распознаётся не каждая передача, значения — нижняя оценка';

// Строка сравнения в духе FotMob: значение лидера на плашке цвета своей команды.
export function StatRow({line}:{line:StatLine}){
 const lead=leader(line);
 const value=(side:'home'|'away')=>{const cell=line[side];
  return <span className={`stat-value ${side}`}><span className={lead===side?`pill ${side}`:undefined}>{cell.text}</span>{cell.note&&<small>{cell.note}</small>}</span>};
 return <div className="stat-row">{value('home')}<span className="stat-label">{line.label}{line.partial&&<span className="partial-mark" title="Разметка категории неполная"> *</span>}
  {line.auto&&<span className="auto-mark" title={AUTO_HINT}>авто</span>}</span>{value('away')}</div>;
}

export function StatCard({title,lines,children,footer,wide}:{title:string;lines?:StatLine[];children?:ReactNode;footer?:ReactNode;wide?:boolean}){
 if(!children&&!lines?.length)return null;
 return <section className={`stat-card${wide?' wide':''}`}><h3>{title}</h3>
  {lines?.map(line=><StatRow key={line.key} line={line}/>)}{children}
  {footer&&<div className="stat-card-foot">{footer}</div>}</section>;
}
