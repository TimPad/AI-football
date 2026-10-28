import {useState,type FormEvent} from 'react';
import {post} from '../../api/client';
import type {Match,Tournament} from '../../api/domain';
import {ErrorBox,Field} from '../../components/ui';
import {HallSelection} from '../halls/HallSelection';
import {BroadcastFields,readBroadcast} from '../matches/BroadcastFields';
import {localInput,zonedToUtc} from '../matches/timezone';
import type {FixtureView} from './api';

export function ScheduleFixtureForm({fixture,tournament,onSaved}:{fixture:FixtureView;tournament:Tournament;onSaved:(m:Match)=>void}){
 const [hallId,setHallId]=useState('');const [cameraId,setCameraId]=useState('');const [error,setError]=useState<unknown>();const [busy,setBusy]=useState(false);
 const [requestId]=useState(()=>crypto.randomUUID());
 async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const f=new FormData(e.currentTarget);setBusy(true);setError(undefined);
  try{onSaved(await post<Match>(`/fixtures/${fixture.id}/schedule`,{request_id:requestId,scheduled_at:zonedToUtc(String(f.get('date')),tournament.timezone),hall_id:hallId,
   camera_profile_id:cameraId||null,referees:String(f.get('referees')??'').split(',').map(v=>v.trim()).filter(Boolean),...readBroadcast(f)}))}
  catch(e){setError(e)}finally{setBusy(false)}}
 return <form onSubmit={submit}><p><b>{fixture.home.label} — {fixture.away.label}</b><br/><span className="muted">{fixture.stage_name} · {fixture.label}</span></p>
  <div className="form-grid"><Field label={`Дата и время · ${tournament.timezone}`}><input required type="datetime-local" name="date" defaultValue={localInput(new Date().toISOString(),tournament.timezone)}/></Field>
   <HallSelection hallId={hallId} cameraId={cameraId} onChange={(h,c)=>{setHallId(h);setCameraId(c)}}/>
   <Field label="Судьи, через запятую"><input name="referees"/></Field><BroadcastFields/></div>
  <ErrorBox error={error}/><button className="primary" disabled={busy||!hallId}>{busy?'Назначаем…':'Назначить матч'}</button></form>;
}
