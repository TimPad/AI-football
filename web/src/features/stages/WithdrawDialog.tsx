import {useEffect,useState} from 'react';
import {post} from '../../api/client';
import {ErrorBox,Modal} from '../../components/ui';
import type {components} from '../../api/types';
import type {StageView,TeamRef} from './api';
import {plural} from './labels';

type Preview=components['schemas']['WithdrawalPreview'];

function consequences(p:Preview){
 const parts=[`Сыграно ${p.played} из ${p.total}.`];
 if(p.rule==='annul')parts.push('Результаты команды будут аннулированы, её не будет в таблице.');
 if(p.rule==='walkover')parts.push(`Сыгранные матчи останутся, ${p.walkovers} ${plural(p.walkovers,'оставшийся будет засчитан','оставшихся будут засчитаны','оставшихся будут засчитаны')} соперникам как технические победы.`);
 if(p.rule==='elimination')parts.push('Соперник в ближайшей паре пройдёт дальше технической победой.');
 if(p.rule==='swiss')parts.push('Сыгранное останется, в следующие туры команда не попадёт.');
 if(p.cancelled_matches)parts.push(`${p.cancelled_matches} ${plural(p.cancelled_matches,'назначенный матч будет отменён','назначенных матча будут отменены','назначенных матчей будут отменены')}.`);
 return parts.join(' ');
}

// Снятие после старта необратимо: сначала предпросмотр правила, затем явное подтверждение.
export function WithdrawDialog({stage,teams,onClose,onDone}:{stage:StageView;teams:TeamRef[];onClose:()=>void;onDone:()=>void}){
 const [team,setTeam]=useState('');const [rule,setRule]=useState<'annul'|'walkover'|null>(null);
 const [preview,setPreview]=useState<Preview|null>(null);const [error,setError]=useState<unknown>();const [busy,setBusy]=useState(false);
 const [requestId]=useState(()=>crypto.randomUUID());
 useEffect(()=>{if(!team){setPreview(null);return}let live=true;setError(undefined);
  post<Preview>(`/stages/${stage.id}/withdrawals/preview`,{entry_id:team,rule}).then(p=>{if(live)setPreview(p)},e=>{if(live)setError(e)});return()=>{live=false}},[team,rule,stage.id]);
 async function confirm(){setBusy(true);setError(undefined);
  try{await post(`/stages/${stage.id}/withdrawals`,{request_id:requestId,entry_id:team,rule,expected_revision:stage.revision});onDone()}catch(e){setError(e)}finally{setBusy(false)}}
 const group=stage.kind==='groups'||stage.kind==='round_robin';
 return <Modal title="Снять команду" sheet onClose={onClose}>
  <label className="field"><span>Команда</span><select value={team} onChange={e=>{setTeam(e.target.value);setRule(null)}}><option value="">Выберите команду</option>{teams.map(t=><option key={t.entry_id} value={t.entry_id}>{t.name}</option>)}</select></label>
  {preview&&group&&<div className="segmented" role="group" aria-label="Что с матчами">{(['annul','walkover'] as const).map(r=><button key={r} type="button" className={preview.rule===r?'active':''} aria-pressed={preview.rule===r} onClick={()=>setRule(r)}>
   {r==='annul'?'Аннулировать':'Технические поражения'}{preview.default_rule===r?' · по правилу':''}</button>)}</div>}
  {preview&&<p role="status">{consequences(preview)}</p>}
  <p className="muted small">Действие нельзя отменить.</p>
  <ErrorBox error={error}/>
  <div className="setup-actions"><button type="button" className="danger" disabled={!preview||busy} onClick={confirm}>Снять команду</button><button type="button" onClick={onClose}>Отмена</button></div>
 </Modal>;
}
