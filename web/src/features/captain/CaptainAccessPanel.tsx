import {useState,type FormEvent} from 'react';
import {api} from '../../api/client';
import {Field,Loading,useLoad} from '../../components/ui';
import {useAuth} from '../auth/Auth';
import {useRatingCommand,CommandStatus} from '../ratings/commands';
import type {Player} from '../../api/domain';
type Access={grants:{id:string,email:string,display_name:string,active:boolean}[],invitations:{id:string,email:string,used_at:string|null,revoked_at:string|null,expires_at:string}[],requests:{id:string,email:string,display_name:string,message:string}[]};
type Proposal={id:string,player_id:string|null,payload:{name:string,birth_date?:string|null,position?:string|null,height_cm?:number|null,weight_kg?:number|null}};
export function CaptainAccessPanel({teamId,players}:{teamId:string,players:Player[]}){
 const {session}=useAuth();const state=useLoad(async()=>{const [access,proposals]=await Promise.all([api<Access>(`/teams/${teamId}/captain-access`),api<{items:Proposal[]}>(`/teams/${teamId}/profile-proposals`)]);return {access,proposals:proposals.items}},teamId);
 const [email,setEmail]=useState('');const [reason,setReason]=useState('Проверено организатором');
 const [matches,setMatches]=useState<Record<string,string>>({});
 const command=useRatingCommand(`aifootball:captain-access-admin:${session!.id}:${teamId}`,()=>{state.reload();setEmail('')});
 async function invite(e:FormEvent){e.preventDefault();await command.execute(`/teams/${teamId}/captain-invitations`,{email})}
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const {access,proposals}=state.data;
 return <section className="surface captain-access-panel"><h2>Капитан команды</h2><p className="muted">Капитан ведёт состав и подтверждает игроков своей команды в выданных заданиях. У команды один активный владелец.</p>
  {access.grants.filter(g=>g.active).map(g=><div className="row wrap" key={g.id}><b>{g.display_name}</b><span>{g.email}</span><button disabled={command.locked||!reason.trim()} onClick={()=>void command.execute(`/teams/${teamId}/captain-grants/${g.id}/revoke`,{reason})}>Отозвать доступ</button></div>)}
  <form onSubmit={invite} className="form-grid"><Field label="Email приглашённого капитана"><input type="email" required maxLength={254} disabled={command.locked} value={email} onChange={e=>setEmail(e.target.value)}/></Field><div><button disabled={command.locked} type="submit">Отправить приглашение</button></div></form>
  {access.invitations.filter(i=>!i.used_at&&!i.revoked_at).map(i=><div className="row wrap" key={i.id}><span>{i.email} · до {new Date(i.expires_at).toLocaleDateString('ru-RU')}</span><button disabled={command.locked||!reason.trim()} onClick={()=>void command.execute(`/teams/${teamId}/captain-invitations/${i.id}/revoke`,{reason})}>Отозвать приглашение</button></div>)}
  <Field label="Причина решения организатора"><input maxLength={1000} required value={reason} disabled={command.locked} onChange={e=>setReason(e.target.value)}/></Field>
  {access.requests.map(r=><article key={r.id}><h3>Запрос доступа: {r.display_name}</h3><p>{r.email} · {r.message}</p><button disabled={command.locked||!reason.trim()} onClick={()=>void command.execute(`/teams/${teamId}/captain-requests/${r.id}/accept`,{reason})}>Предоставить доступ к этой команде</button></article>)}
  {proposals.length>0&&<><h3>Предложения по карточкам игроков</h3>{proposals.map(p=><article className="captain-profile-proposal" key={p.id}><b>{p.player_id?`Сейчас: ${players.find(v=>v.id===p.player_id)?.name??'Карточка игрока'} → Предложено: ${p.payload.name}`:p.payload.name}</b><p className="muted">{[p.payload.birth_date,p.payload.position,p.payload.height_cm?`${p.payload.height_cm} см`:null,p.payload.weight_kg?`${p.payload.weight_kg} кг`:null].filter(Boolean).join(' · ')}</p>
   {!p.player_id&&<Field label={`Решение по игроку ${p.payload.name}`}><select value={matches[p.id]??''} disabled={command.locked} onChange={e=>setMatches(old=>({...old,[p.id]:e.target.value}))}><option value="">Выберите человека или создание нового</option><option value="new">Создать нового человека</option>{players.filter(v=>!v.archived).map(v=><option value={v.id} key={v.id}>{v.name} · {v.birth_date??'Дата рождения не указана'}</option>)}</select></Field>}
   <button disabled={command.locked||!reason.trim()||!p.player_id&&!matches[p.id]} onClick={()=>void command.execute(`/teams/${teamId}/profile-proposals/${p.id}/accept`,{reason,create_new:!p.player_id&&matches[p.id]==='new',use_existing_player_id:!p.player_id&&matches[p.id]!=='new'?matches[p.id]:null})}>{p.player_id?'Принять исправления карточки':'Добавить выбранного игрока в команду'}</button></article>)}</>}
  <CommandStatus command={command}/>
 </section>;
}
