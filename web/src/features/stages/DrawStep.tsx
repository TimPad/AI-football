import {useState} from 'react';
import {ApiError,post} from '../../api/client';
import type {Entry} from '../../api/domain';
import {ErrorBox} from '../../components/ui';
import type {DrawPreview,StageView} from './api';
import {PairCard} from './Bracket';
import './stages.css';

type Method='pots'|'snake'|'seeded'|'random'|'scheme'|'manual';
type Source={entry?:string;group?:number;place?:number;best?:number;rank?:number;stage_place?:number}|null;
const LETTERS='ABCDEFGHIJKLMNOP';

function methodsFor(stage:StageView):[Method,string][]{
 const previous=(stage.config as {source?:{previous?:boolean}}|null)?.source?.previous;
 if(stage.kind==='groups')return [['pots','По корзинам'],['snake','Змейкой']];
 if(stage.kind==='swiss')return [['seeded','По посеву'],['random','Случайно']];
 if(stage.kind==='round_robin')return [['random','Случайно'],['seeded','По посеву']];
 return previous?[['scheme','По схеме'],['seeded','По посеву'],['random','Случайно']]:[['seeded','По посеву'],['random','Случайно']];
}

export function sourceName(source:Source|string,names:Record<string,string>){
 if(source===null)return 'Пропуск хода';
 if(typeof source==='string')return names[source]??'Команда';
 if(source.entry)return names[source.entry]??'Команда';
 if(source.group)return `${LETTERS[source.group-1]}${source.place}`;
 if(source.best)return `Лучшая ${source.best}-я №${source.rank}`;
 if(source.stage_place)return `${source.stage_place}-е место`;
 return 'Соперник определится';
}

export function DrawStep({stage,entries,timezone,onSaved}:{stage:StageView;entries:Entry[];timezone:string;onSaved:()=>void}){
 const names=Object.fromEntries(entries.map(e=>[e.id,e.team.name]));
 const methods=methodsFor(stage);const previous=methods[0][0]==='scheme';
 const [seeding,setSeeding]=useState<string[]>(()=>previous?[]:((stage.draw?.seeding as string[]|undefined)??entries.map(e=>e.id)));
 const [method,setMethod]=useState<Method>(methods[0][0]);
 const [seed,setSeed]=useState(()=>Math.floor(Math.random()*1e9));
 const [preview,setPreview]=useState<DrawPreview|null>(null);const [picked,setPicked]=useState<string|null>(null);
 const [error,setError]=useState<unknown>();const [busy,setBusy]=useState(false);const [requestId,setRequestId]=useState(()=>crypto.randomUUID());
 const move=(i:number,d:number)=>{const next=[...seeding];[next[i],next[i+d]]=[next[i+d],next[i]];setSeeding(next);setPreview(null)};
 async function run(body:{method:Method;seed:number;placement?:unknown[]}){setBusy(true);setError(undefined);
  try{setPreview(await post<DrawPreview>(`/stages/${stage.id}/draw/preview`,{...body,seeding}));setRequestId(crypto.randomUUID())}catch(e){setError(e)}finally{setBusy(false)}}
 // Касание двух команд меняет их местами; жеребьёвка становится ручной.
 function tap(id:string){
  if(!preview)return;if(picked===null){setPicked(id);return}
  if(picked===id){setPicked(null);return}
  const placement=structuredClone(preview.placement) as unknown[];const key=(x:unknown)=>JSON.stringify(x);
  const find=(target:string):[number,number]=>{for(let g=0;g<placement.length;g++){const item=placement[g];if(Array.isArray(item)){const i=item.findIndex(x=>key(x)===target);if(i>=0)return [g,i]}else if(key(item)===target)return [g,-1]}return [-1,-1]};
  const [ga,ia]=find(picked),[gb,ib]=find(id);setPicked(null);
  if(ga<0||gb<0)return;
  const get=(g:number,i:number)=>i<0?placement[g]:(placement[g] as unknown[])[i];
  const set=(g:number,i:number,v:unknown)=>{if(i<0)placement[g]=v;else (placement[g] as unknown[])[i]=v};
  const a=get(ga,ia),b=get(gb,ib);set(ga,ia,b);set(gb,ib,a);
  void run({method:'manual',seed,placement});
 }
 async function confirm(){if(!preview)return;setBusy(true);setError(undefined);
  try{await post(`/stages/${stage.id}/draw`,{request_id:requestId,expected_revision:stage.revision,method:preview.method,seed:preview.seed,seeding,placement:preview.method==='manual'?preview.placement:null});onSaved()}
  catch(e){setError(e instanceof ApiError&&e.status===409&&e.code==='draw_locked'?'Жеребьёвку нельзя изменить: в этапе уже есть подтверждённый результат':e)}finally{setBusy(false)}}
 const pot=(id:string)=>preview?.pots?.[id];
 return <section className="draw-step surface" aria-label={`Жеребьёвка: ${stage.name}`}>
  <h2>Жеребьёвка · {stage.name}</h2>
  {!previous&&<details open={!stage.draw}><summary>Посев · сильнейшие сверху</summary><ol className="seeding">{seeding.map((id,i)=><li key={id}><b>{i+1}</b><span>{names[id]}</span>
   <button type="button" aria-label={`${names[id]} выше`} disabled={!i} onClick={()=>move(i,-1)}>↑</button>
   <button type="button" aria-label={`${names[id]} ниже`} disabled={i===seeding.length-1} onClick={()=>move(i,1)}>↓</button></li>)}</ol></details>}
  {methods.length>1&&<div className="segmented" role="group" aria-label="Способ">{methods.map(([id,label])=><button key={id} type="button" className={method===id?'active':''} aria-pressed={method===id} onClick={()=>{setMethod(id);setPreview(null)}}>{label}</button>)}</div>}
  <div className="setup-actions"><button type="button" className={preview?'':'primary'} disabled={busy} onClick={()=>run({method,seed})}>Провести жеребьёвку</button>
   {preview&&(method==='pots'||method==='random')&&<button type="button" disabled={busy} onClick={()=>{const next=Math.floor(Math.random()*1e9);setSeed(next);void run({method,seed:next})}}>Перетянуть</button>}</div>
  {preview&&<>
   <p className="muted small">Коснитесь двух команд, чтобы поменять их местами.</p>
   {preview.groups.length>0?<div className="draw-groups">{(preview.placement as string[][]).map((group,g)=><div className="draw-group" key={g}><h3>Группа {LETTERS[g]}</h3>
    {group.map(id=><button type="button" key={id} className="draw-team" data-pot={pot(id)} aria-pressed={picked===JSON.stringify(id)} onClick={()=>tap(JSON.stringify(id))}>{names[id]}</button>)}</div>)}</div>
   :stage.kind==='single_elim'||stage.kind==='double_elim'?<div className="draw-groups"><div className="draw-group"><h3>Места в сетке по силе</h3>
    {(preview.placement as Source[]).map((src,i)=><button type="button" key={i} className="draw-team" aria-pressed={picked===JSON.stringify(src)} onClick={()=>tap(JSON.stringify(src))}>{i+1}. {sourceName(src,names)}</button>)}</div>
    <div className="draw-group"><h3>Первый раунд</h3>{preview.pairs.filter(p=>p.round_no===1&&(p.bracket==='upper'||!p.bracket)).map(p=><PairCard key={p.key} pair={p} timezone={timezone}/>)}</div></div>
   :<div className="draw-groups"><div className="draw-group"><h3>Порядок</h3>{(preview.placement as string[]).map(id=><button type="button" key={id} className="draw-team" aria-pressed={picked===JSON.stringify(id)} onClick={()=>tap(JSON.stringify(id))}>{names[id]}</button>)}</div>
    <div className="draw-group"><h3>Тур 1</h3>{preview.pairs.filter(p=>p.round_no===1&&!p.bye).map(p=><PairCard key={p.key} pair={p} timezone={timezone}/>)}</div></div>}
   {(preview.kept>0||preview.cancelled>0)&&<p className="warning" role="status">Сохранятся назначенных матчей: {preview.kept}. Будут отменены: {preview.cancelled}.</p>}
   <div className="setup-actions"><button type="button" className="primary" disabled={busy} onClick={confirm}>Подтвердить жеребьёвку</button></div></>}
  <ErrorBox error={error}/>
 </section>;
}
