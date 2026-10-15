import {useState} from 'react';
import {Radio,ExternalLink} from 'lucide-react';
import type {PublicMatch} from '../../api/domain';
import {Empty} from '../../components/ui';

// iframe создаётся только по нажатию; ссылка ВК остаётся запасным путём.
export function Broadcast({match:m}:{match:PublicMatch}){
 const [playing,setPlaying]=useState(false);const watchUrl=m.broadcast_url||m.broadcast_embed_url;
 return <section className="broadcast-section"><div className="panel-head"><h2><Radio/>Трансляция матча</h2>{watchUrl&&<a className="public-action" href={watchUrl} target="_blank" rel="noopener noreferrer">Смотреть в ВК<ExternalLink/></a>}</div>
  {m.broadcast_embed_url?<><div className="broadcast-player">{playing?<iframe src={m.broadcast_embed_url} title={`Трансляция: ${m.home_name} — ${m.away_name}`} allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowFullScreen referrerPolicy="strict-origin-when-cross-origin"/>
   :<div className="broadcast-cover"><Radio/><h3>Трансляция ВК</h3><p>Видео загружается только после нажатия</p><button className="primary" onClick={()=>setPlaying(true)}>Смотреть на сайте</button></div>}</div>
   <p className="muted">Если плеер недоступен, откройте трансляцию в ВК.</p></>
  :<Empty>{m.broadcast_url?'Трансляция доступна по ссылке в ВК.':'Ссылка на трансляцию появится здесь, когда её добавит организатор.'}</Empty>}</section>;
}
