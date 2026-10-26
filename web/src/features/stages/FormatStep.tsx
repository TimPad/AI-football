import {useState,type FormEvent} from 'react';
import {post} from '../../api/client';
import type {RegVersion} from '../../api/domain';
import {Check,ErrorBox,Field} from '../../components/ui';
import type {Standings,Template} from './api';
import './stages.css';

// Числа хранятся строками, пока их вводят; ограничения применяются при сохранении.
type Params={template:Template;group_count:string;per_group:string;best_thirds:string;legs:1|2;third_place:boolean;grand_final_reset:boolean;rounds:string;with_playoff:boolean;playoff_teams:string;regulation_id:string;playoff_regulation_id:string};
const TEMPLATES:{id:Template;name:string;hint:string;scheme:string}[]=[
 {id:'league',name:'Лига',hint:'Каждый с каждым, места по очкам',scheme:'aaaa'},
 {id:'groups_playoff',name:'Группы и плей-офф',hint:'Группы, затем сетка на выбывание',scheme:'aa-b'},
 {id:'playoff',name:'Плей-офф',hint:'Сетка на выбывание с первого матча',scheme:'bbbb'},
 {id:'double_elim',name:'Двойное выбывание',hint:'Выбывают после двух поражений',scheme:'bb-bb'},
 {id:'swiss',name:'Швейцарская система',hint:'Соперники по очкам, без повторов',scheme:'a-a-a'},
];
const num=(value:string,min:number,max:number)=>Math.max(min,Math.min(max,Number(value)||min));

export function FormatStep({tid,regulations,standings,onSaved}:{tid:string;regulations:RegVersion[];standings:Standings;onSaved:()=>void}){
 const locked=standings.stages.some(s=>s.draw);
 const [p,setP]=useState<Params>({template:'groups_playoff',group_count:'2',per_group:'2',best_thirds:'0',legs:1,third_place:false,grand_final_reset:false,rounds:'4',with_playoff:false,playoff_teams:'4',
  regulation_id:regulations[0]?.id??'',playoff_regulation_id:''});
 const [requestId,setRequestId]=useState(()=>crypto.randomUUID());const [busy,setBusy]=useState(false);const [error,setError]=useState<unknown>();
 const change=(next:Partial<Params>)=>{setP({...p,...next});setRequestId(crypto.randomUUID())};
 async function submit(e:FormEvent){e.preventDefault();setBusy(true);setError(undefined);
  const body={request_id:requestId,template:p.template,regulation_id:p.regulation_id,playoff_regulation_id:p.playoff_regulation_id||null,group_count:num(p.group_count,2,16),per_group:num(p.per_group,1,16),
   best_thirds:num(p.best_thirds,0,16),legs:p.legs,third_place:p.third_place,grand_final_reset:p.grand_final_reset,rounds:p.template==='swiss'?num(p.rounds,1,15):null,
   playoff_teams:p.with_playoff&&(p.template==='league'||p.template==='swiss')?num(p.playoff_teams,2,64):null};
  try{await post(`/tournaments/${tid}/format`,body);onSaved()}catch(e){setError(e)}finally{setBusy(false)}}
 const playoff=p.template==='groups_playoff'||p.template==='playoff'||p.with_playoff;
 return <form className="surface format-step" onSubmit={submit}>
  <h2>Формат турнира</h2>
  {locked&&<p className="muted">Формат закреплён жеребьёвкой.</p>}
  <div className="format-cards" role="radiogroup" aria-label="Формат">{TEMPLATES.map(t=><button key={t.id} type="button" role="radio" className="format-card" aria-checked={p.template===t.id}
   aria-disabled={locked} disabled={locked} onClick={()=>change({template:t.id})}><strong>{t.name}</strong><span>{t.hint}</span>
   <span className="format-scheme" aria-hidden="true">{[...t.scheme].map((c,i)=><i key={i} className={c==='b'?'accent':c==='-'?'gap':undefined}/>)}</span></button>)}</div>
  <fieldset className="team-fieldset" disabled={locked||busy}><div className="form-grid">
   {p.template==='groups_playoff'&&<><Field label="Групп"><input type="number" min={2} max={16} value={p.group_count} onChange={e=>change({group_count:e.target.value})}/></Field>
    <Field label="Выходят из группы"><input type="number" min={1} max={16} value={p.per_group} onChange={e=>change({per_group:e.target.value})}/></Field>
    <Field label={`Лучшие ${num(p.per_group,1,16)+1}-и места`}><input type="number" min={0} max={16} value={p.best_thirds} onChange={e=>change({best_thirds:e.target.value})}/></Field></>}
   {(p.template==='league'||p.template==='groups_playoff')&&<Field label="Круги"><select value={p.legs} onChange={e=>change({legs:Number(e.target.value) as 1|2})}><option value={1}>Один круг</option><option value={2}>Два круга</option></select></Field>}
   {p.template==='swiss'&&<Field label="Туров"><input type="number" min={1} max={15} value={p.rounds} onChange={e=>change({rounds:e.target.value})}/></Field>}
   {(p.template==='league'||p.template==='swiss')&&<><Check label="Добавить плей-офф" checked={p.with_playoff} onChange={v=>change({with_playoff:v})}/>
    {p.with_playoff&&<Field label="В плей-офф выходят"><input type="number" min={2} max={64} value={p.playoff_teams} onChange={e=>change({playoff_teams:e.target.value})}/></Field>}</>}
   {playoff&&<Check label="Матч за 3-е место" checked={p.third_place} onChange={v=>change({third_place:v})}/>}
   {p.template==='double_elim'&&<Check label="Переигровка финала, если победит команда из нижней сетки" checked={p.grand_final_reset} onChange={v=>change({grand_final_reset:v})}/>}
   <Field label="Регламент матчей"><select required value={p.regulation_id} onChange={e=>change({regulation_id:e.target.value})}>{regulations.map(r=><option key={r.id} value={r.id}>{r.variant_name} · версия {r.version}</option>)}</select></Field>
   {(p.template==='groups_playoff'||p.with_playoff&&(p.template==='league'||p.template==='swiss'))&&<Field label="Регламент плей-офф"><select value={p.playoff_regulation_id} onChange={e=>change({playoff_regulation_id:e.target.value})}>
    <option value="">Тот же</option>{regulations.map(r=><option key={r.id} value={r.id}>{r.variant_name} · версия {r.version}</option>)}</select></Field>}
  </div></fieldset>
  <ErrorBox error={error}/>
  {!locked&&<div className="setup-actions"><button className="primary" disabled={busy||!p.regulation_id}>{busy?'Сохраняем…':standings.stages.length?'Заменить формат':'Сохранить формат'}</button>
   {standings.stages.length>0&&<span className="muted small">Сейчас: {standings.stages.map(s=>s.name).join(' → ')}</span>}</div>}
 </form>;
}
