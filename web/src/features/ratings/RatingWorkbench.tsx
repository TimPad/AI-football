import {useState} from 'react';
import {api} from '../../api/client';
import type {Match} from '../../api/domain';
import {useLoad,Loading,Check} from '../../components/ui';
import {ParticipationEditor} from './ParticipationEditor';
import {ActionReview} from './ActionReview';
import {MatchRatings} from './MatchRating';
import {CommandStatus,useRatingCommand} from './commands';
import type {Actions,Participation,Analytics} from './types';
export function RatingWorkbench({matchId,actorId}:{matchId:string,actorId:string}){
 const [tab,setTab]=useState('participation');const [tick,setTick]=useState(0);
 return <div className="ratings"><div className="tabs">{[['participation','Участие и роли'],['actions','Действия и полнота'],['ratings','Оценки игроков'],['publication','Публикация статистики']].map(([key,label])=><button key={key} className={tab===key?'active':''} onClick={()=>setTab(key)}>{label}</button>)}</div>{tab==='participation'&&<ParticipationEditor matchId={matchId} actorId={actorId} onSaved={()=>setTick(n=>n+1)}/>} {tab==='actions'&&<ActionReview key={tick} matchId={matchId} actorId={actorId} onSaved={()=>setTick(n=>n+1)}/>} {tab==='ratings'&&<MatchRatings matchId={matchId} refresh={tick}/>} {tab==='publication'&&<Publication matchId={matchId} actorId={actorId}/>}</div>
}
function Publication({matchId,actorId}:{matchId:string,actorId:string}){
 const state=useLoad(async()=>{const [match,part,actions]=await Promise.all([api<Match>(`/matches/${matchId}`),api<Participation>(`/matches/${matchId}/participation`),api<Actions>(`/matches/${matchId}/performance-actions`)]);const analytics=await api<Analytics>(`/tournaments/${match.tournament_id}/analytics`);return {match,part,actions,analytics}},matchId);
 const [partId,setPart]=useState('');const [actionId,setAction]=useState('');const [approve,setApprove]=useState(false);
 const command=useRatingCommand(`aifootball:rating-publication:${actorId}:${matchId}`,()=>state.reload());
 if(!state.data)return <Loading error={state.error} retry={state.reload}/>;const d=state.data;
 return <section className="surface"><h2>Разрешить статистику для сайта</h2><p>Выберите подтверждённые версии. Протокол и связанный видеоотчёт должны быть опубликованы отдельно. Закрытые заметки и кадры в таблицу рейтинга не попадут.</p><label className="field"><span>Публикуемая версия участия</span><select aria-label="Публикуемая версия участия" disabled={command.locked} value={partId} onChange={e=>setPart(e.target.value)}><option value="">Не выбрана</option>{d.part.versions.filter(p=>p.status==='confirmed').map(p=><option key={p.id} value={p.id}>Участие №{p.revision}</option>)}</select></label><label className="field"><span>Публикуемая версия действий</span><select aria-label="Публикуемая версия действий" disabled={command.locked} value={actionId} onChange={e=>setAction(e.target.value)}><option value="">Не выбрана</option>{d.actions.versions.filter(p=>p.status==='confirmed').map(p=><option key={p.id} value={p.id}>Действия №{p.revision}</option>)}</select></label><Check label="Разрешить текущую пилотную методику для публичного расчёта" checked={approve} onChange={setApprove}/><button className="primary" disabled={command.locked||!partId||!actionId} onClick={()=>void command.execute(`/matches/${matchId}/performance-publication`,{expected_revision:d.analytics.revision,expected_match_revision:d.match.revision,participation_version_id:partId,action_version_id:actionId,approve_policy:approve},'PUT')}>Разрешить выбранные данные</button><p className="muted">После этого рассчитайте публичный срез и опубликуйте рейтинг на странице турнира.</p><CommandStatus command={command}/></section>
}
