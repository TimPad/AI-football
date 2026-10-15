import {useState} from 'react';
import {useParams} from 'react-router-dom';
import {useQueryPatch} from '../navigation/useQueryPatch';
import {PlayerRatingHistory} from '../ratings/PlayerRatingHistory';
import {isUuid} from '../navigation/query';

// Публичная история опубликованных оценок; без входа и без приватного каталога.
export function PublicPlayerHistoryPage(){
 const {id=''}=useParams();const [params,update]=useQueryPatch();const [name,setName]=useState<string|null>(null);
 if(!isUuid(id))return <div className="block-error" role="alert">Неверная ссылка на игрока.</div>;
 const tid=isUuid(params.get('tournament_id'))?params.get('tournament_id')!:'';
 const snapshot=isUuid(params.get('snapshot_id'))?params.get('snapshot_id')!:'';
 return <div className="player-history-page">
  <p className="muted">История оценок турнира</p>
  <h1>{name??'Игрок'}</h1>
  <PlayerRatingHistory key={id} playerId={id} publicView initialTournament={tid} initialSnapshot={snapshot} onName={setName}
   onContext={(t,s)=>update({tournament_id:t||null,snapshot_id:s||null},{replace:true})}/>
 </div>;
}
