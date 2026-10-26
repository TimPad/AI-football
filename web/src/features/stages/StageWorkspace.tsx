import {useState} from 'react';
import {api,post} from '../../api/client';
import type {Entry,RegVersion,Tournament} from '../../api/domain';
import {Empty,ErrorBox,Loading,Modal,useLoad} from '../../components/ui';
import type {GroupView,PairView,StageView,Standings} from './api';
import {DrawStep} from './DrawStep';
import {FormatStep} from './FormatStep';
import {StageBlock} from './StandingsView';
import {STATUS} from './labels';
import './stages.css';

export function useCabinetStandings(tid:string){return useLoad(()=>api<Standings>(`/tournaments/${tid}/stages`),`stages-${tid}`)}

function LotDialog({stage,group,onSaved}:{stage:StageView;group:GroupView;onSaved:()=>void}){
 const [order,setOrder]=useState(()=>group.rows.filter(r=>r.tied).map(r=>r.team));const [error,setError]=useState<unknown>();const [requestId]=useState(()=>crypto.randomUUID());
 const move=(i:number,d:number)=>{const next=[...order];[next[i],next[i+d]]=[next[i+d],next[i]];setOrder(next)};
 async function save(){try{await post(`/stages/${stage.id}/lots`,{request_id:requestId,group:String(group.group_no),order:order.map(t=>t.entry_id)});onSaved()}catch(e){setError(e)}}
 return <><p className="muted">Расставьте команды по результату жребия.</p><ol className="seeding">{order.map((t,i)=><li key={t.entry_id}><b>{i+1}</b><span>{t.name}</span>
  <button type="button" aria-label={`${t.name} выше`} disabled={!i} onClick={()=>move(i,-1)}>↑</button>
  <button type="button" aria-label={`${t.name} ниже`} disabled={i===order.length-1} onClick={()=>move(i,1)}>↓</button></li>)}</ol>
  <ErrorBox error={error}/><button className="primary" onClick={save}>Сохранить жребий</button></>;
}

function ReplaceDialog({pair,entries,onSaved}:{pair:PairView;entries:Entry[];onSaved:()=>void}){
 const leg=pair.legs.find(l=>l.fixture_id);const [side,setSide]=useState<'home'|'away'>('home');const [entry,setEntry]=useState('');const [error,setError]=useState<unknown>();
 const [requestId]=useState(()=>crypto.randomUUID());
 async function save(){if(!leg?.fixture_id)return;try{await post(`/fixtures/${leg.fixture_id}/replace`,{request_id:requestId,side,entry_id:entry});onSaved()}catch(e){setError(e)}}
 return <><p>{pair.label}: {pair.home.label} — {pair.away.label}</p><div className="form-grid">
  <label className="field"><span>Сторона</span><select value={side} onChange={e=>setSide(e.target.value as 'home'|'away')}><option value="home">{pair.home.label}</option><option value="away">{pair.away.label}</option></select></label>
  <label className="field"><span>Новая команда</span><select value={entry} onChange={e=>setEntry(e.target.value)}><option value="" disabled>Выберите команду</option>{entries.map(e=><option key={e.id} value={e.id}>{e.team.name}</option>)}</select></label></div>
  <ErrorBox error={error}/><button className="primary" disabled={!entry} onClick={save}>Заменить команду</button></>;
}

// Вкладка «Таблица» кабинета: формат, жеребьёвка, таблицы и сетка по подтверждённым протоколам.
export function StageWorkspace({tournament,entries,regulations}:{tournament:Tournament;entries:Entry[];regulations:RegVersion[]}){
 const state=useCabinetStandings(tournament.id);
 const [drawing,setDrawing]=useState<StageView|null>(null);const [lot,setLot]=useState<[StageView,GroupView]|null>(null);
 const [replacing,setReplacing]=useState<PairView|null>(null);const [editFormat,setEditFormat]=useState(false);const [error,setError]=useState<unknown>();
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const data=state.data;
 const done=()=>{setDrawing(null);setLot(null);setReplacing(null);setEditFormat(false);state.reload()};
 async function nextRound(stage:StageView){setError(undefined);try{await post(`/stages/${stage.id}/next-round`,{request_id:crypto.randomUUID(),expected_revision:stage.revision});state.reload()}catch(e){setError(e)}}
 if(!regulations.length)return <Empty>Сначала добавьте регламент турнира.</Empty>;
 if(!data.stages.length||editFormat)return <FormatStep tid={tournament.id} regulations={regulations} standings={data} onSaved={done}/>;
 const locked=data.stages.some(s=>s.draw);
 return <div className="standings">
  {!locked&&<div className="setup-actions"><button type="button" onClick={()=>setEditFormat(true)}>Изменить формат</button></div>}
  <ErrorBox error={error}/>
  {data.stages.map((stage,i)=><section key={stage.id} className="stage-block">
   <div className="page-head"><div><h2>{stage.name}</h2><p className="muted">{STATUS[stage.status]}</p></div>
    <div className="row">{stage.status!=='completed'&&stage.status!=='started'&&<button type="button" className={stage.draw?'':'primary'} onClick={()=>setDrawing(stage)}>{stage.draw?'Изменить жеребьёвку':'Провести жеребьёвку'}</button>}
     {stage.can_next_round&&<button type="button" className="primary" onClick={()=>nextRound(stage)}>Следующий тур</button>}
     {stage.groups.filter(g=>g.needs_lot).map(g=><button type="button" key={g.group_no} onClick={()=>setLot([stage,g])}>Ввести жребий · {g.name}</button>)}</div></div>
   {stage.draw?<StageBlock stage={stage} next={data.stages[i+1]} timezone={tournament.timezone} matchHref={id=>`/matches/${id}`}
    action={p=>p.changed?<button type="button" onClick={()=>setReplacing(p)}>Заменить команду</button>:null}/>:<p className="muted">Пары появятся после жеребьёвки.</p>}
  </section>)}
  {drawing&&<Modal title="Жеребьёвка" onClose={()=>setDrawing(null)}><DrawStep stage={drawing} entries={entries} timezone={tournament.timezone} onSaved={done}/></Modal>}
  {lot&&<Modal title={`Жребий · ${lot[1].name}`} onClose={()=>setLot(null)}><LotDialog stage={lot[0]} group={lot[1]} onSaved={done}/></Modal>}
  {replacing&&<Modal title="Заменить команду" onClose={()=>setReplacing(null)}><ReplaceDialog pair={replacing} entries={entries} onSaved={done}/></Modal>}
 </div>;
}
