import {useState} from 'react';
import {Check} from '../../components/ui';
import {FIELD_LABELS,type ImportView,type ImportConfig} from './types';

export function ImportPreview({value,config,onChange,disabled}:{value:ImportView,config:ImportConfig,onChange:(c:ImportConfig)=>void,disabled:boolean}){
 const [filter,setFilter]=useState('all');
 function edit(id:string,key:string,text:string){onChange({...config,edits:{...config.edits,[id]:{...config.edits?.[id],[key]:text}}})}
 const rows=value.rows.map(row=>({...row,issues:row.issues??[],player_candidates:row.player_candidates??[],team_candidates:row.team_candidates??[]})).filter(row=>filter==='all'||filter==='errors'&&row.issues.length>0||filter==='matches'&&(row.player_candidates.length>0||row.team_candidates.length>0)||filter==='excluded'&&config.excluded_rows?.includes(row.id));
 return <section className="surface import-preview"><div className="panel-head"><h2>Строки состава</h2><select aria-label="Показать строки" value={filter} onChange={e=>setFilter(e.target.value)}>
  <option value="all">Все строки</option><option value="errors">Ошибки</option><option value="matches">Возможные совпадения</option><option value="excluded">Пропущенные</option></select></div>
  <div className="import-table-scroll" tabIndex={0} aria-label="Таблица импорта"><table><thead><tr><th>Строка</th><th>Команда</th><th>Игрок</th><th>№</th><th>Проверка</th></tr></thead><tbody>{rows.map(row=>{
   const excluded=Boolean(config.excluded_rows?.includes(row.id));const decision=config.decisions?.[row.id];
   const fieldValue=(key:string)=>config.edits?.[row.id]?.[key]??row.values?.[key]??(key==='name'?row.name:key==='shirt_number'?row.shirt_number:'')??'';
   return <tr key={row.id} className={excluded?'import-excluded':''} id={`import-row-${row.id.replace(/:/g,'-')}`}>
    <td className="num">{row.source_row}<Check disabled={disabled} label={`Пропустить строку ${row.source_row}`} checked={excluded} onChange={checked=>onChange({...config,
     excluded_rows:checked?[...(config.excluded_rows??[]),row.id]:(config.excluded_rows??[]).filter(id=>id!==row.id)})}/></td>
    <td>{value.scope==='tournament'&&!value.entry_id?<input disabled={disabled||excluded} aria-label={`Команда, строка ${row.source_row}`}
     value={config.edits?.[row.id]?.team??row.team_name} onChange={e=>edit(row.id,'team',e.target.value)}/>:row.team_name}
     {row.team_candidates.length>0&&!value.entry_id&&<select disabled={disabled||excluded} aria-label={`Выбор команды, строка ${row.source_row}`}
      value={config.team_decisions?.[row.team_name]??''} onChange={e=>onChange({...config,team_decisions:{...config.team_decisions,[row.team_name]:e.target.value}})}>
      <option value="">Выберите команду</option><option value="new">Создать другую команду</option>{row.team_candidates.map(t=><option key={t.id} value={t.id}>{t.name}{t.archived?' · архив':''}</option>)}
     </select>}</td>
    <td><input disabled={disabled||excluded} aria-label={`ФИО, строка ${row.source_row}`} value={fieldValue('name')} onChange={e=>edit(row.id,'name',e.target.value)}/>
     {(row.player_candidates.length>0||row.issues.some(i=>i.includes('ФИО повторяется'))||decision)&&<select disabled={disabled||excluded}
      aria-label={`Выбор игрока, строка ${row.source_row}`} value={decision?.create_new?'new':decision?.player_id??''}
      onChange={e=>onChange({...config,decisions:{...config.decisions,[row.id]:e.target.value==='new'?{create_new:true}:e.target.value?{player_id:e.target.value}:{}}})}>
      <option value="">Выберите решение</option><option value="new">Создать нового игрока</option>{row.player_candidates.map(p=><option key={p.id} value={p.id}>{p.name}{p.archived?' · архив':''}</option>)}
     </select>}
     <details><summary>Данные игрока</summary>{['position','birth_date','height_cm','weight_kg'].map(key=><label className="field" key={key}><span>{FIELD_LABELS[key]}</span>
      <input disabled={disabled||excluded} aria-label={`${FIELD_LABELS[key]}, строка ${row.source_row}`} value={fieldValue(key)} onChange={e=>edit(row.id,key,e.target.value)}/></label>)}</details>
    </td><td><input disabled={disabled||excluded} className="import-number" aria-label={`Номер, строка ${row.source_row}`} value={fieldValue('shirt_number')} onChange={e=>edit(row.id,'shirt_number',e.target.value)}/></td>
    <td>{excluded?<span className="muted">Будет пропущена</span>:row.issues.length?<ul className="import-issues">{row.issues.map(issue=><li key={issue}>{issue}</li>)}</ul>:<span className="chip ok">{row.action}</span>}</td>
   </tr>;
  })}</tbody></table></div>{!rows.length&&<p className="empty">Строк с такими условиями нет.</p>}
 </section>;
}
