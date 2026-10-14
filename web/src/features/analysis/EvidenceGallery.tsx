import {useState} from 'react';
import type {Evidence} from './understandingTypes';
import {clock} from './understandingTypes';
export function EvidenceGallery({matchId,runId,evidence}:{matchId:string,runId:string,evidence:Evidence[]}){
 return <div className="evidence-gallery">{evidence.map(item=><EvidenceImage key={item.id} matchId={matchId} runId={runId} item={item}/>)}{!evidence.length&&<p className="muted">Кадры для этого эпизода не приложены.</p>}</div>;
}
function EvidenceImage({matchId,runId,item}:{matchId:string,runId:string,item:Evidence}){
 const [failed,setFailed]=useState(false);
 return <figure>{failed?<p className="warning">Не удалось загрузить кадр. Обновите страницу для повтора.</p>:<img loading="lazy" src={`/api/v1/matches/${matchId}/analysis/runs/${runId}/understanding/evidence/${encodeURIComponent(item.id)}`} alt={`Кадр ${item.frame_id} · ${clock(item.video_ms)}`} onError={()=>setFailed(true)}/>}<figcaption>{clock(item.video_ms)} исходника · кадр {item.frame_id}{item.crop&&' · область игрока'}</figcaption></figure>;
}
