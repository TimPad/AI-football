import {Field} from '../../components/ui';
import {FIELD_LABELS,inferMapping,type ImportView,type ImportConfig} from './types';

export function ImportMapping({value,config,onChange,disabled}:{value:ImportView,config:ImportConfig,onChange:(c:ImportConfig)=>void,disabled:boolean}){
 const sheet=value.sheets.find(s=>s.name===config.sheet)??value.sheets[0];
 const field=(name:string)=><Field key={name} label={`Столбец: ${FIELD_LABELS[name]}`}><select disabled={disabled}
  value={config.mapping[name]??''} onChange={e=>{const mapping={...config.mapping};if(e.target.value==='')delete mapping[name];else mapping[name]=Number(e.target.value);onChange({...config,mapping})}}>
  <option value="">Не загружать</option>{sheet?.headers.map((label,index)=><option key={index} value={index}>{label||`Столбец ${index+1}`}</option>)}
 </select></Field>;
 return <details className="surface import-mapping" open={!value.rows.length}>
  <summary><b>Лист и столбцы</b><span className="muted"> · {config.sheet}</span></summary>
  <Field label="Лист Excel"><select disabled={disabled} value={config.sheet} onChange={e=>{const selected=value.sheets.find(s=>s.name===e.target.value)!;
   onChange({sheet:selected.name,mapping:inferMapping(selected.headers),edits:{},decisions:{},team_decisions:{},excluded_rows:[]})}}>
   {value.sheets.map(s=><option key={s.name} value={s.name}>{s.name} · строк: {s.row_count}</option>)}
  </select></Field>
  <div className="form-grid">{(value.scope==='tournament'&&!value.entry_id?['team','name','shirt_number','position']:['name','shirt_number','position']).map(field)}</div>
  <details><summary>Раздельное ФИО и дополнительные данные</summary><div className="form-grid">{['last_name','first_name','patronymic','birth_date','height_cm','weight_kg'].map(field)}</div></details>
 </details>;
}
