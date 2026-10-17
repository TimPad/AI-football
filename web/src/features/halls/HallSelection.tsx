import {useState} from 'react';
import {HallEditor} from './HallPage';
import {YandexMapsLink} from '../../components/YandexMapsLink';
import {Link} from 'react-router-dom';
import {all} from '../../api/client';
import type {Hall,CameraProfile} from '../../api/domain';
import {useLoad,Loading,Field,Modal} from '../../components/ui';
export function HallSelection({hallId,cameraId,onChange,snapshot,required=true}:{hallId:string,cameraId:string,onChange:(hallId:string,cameraId:string)=>void,snapshot?:Hall|null,required?:boolean}){
 const [creating,setCreating]=useState(false);
 const halls=useLoad(()=>all<Hall>('/halls'),'halls');
 const profiles=useLoad(()=>hallId?all<CameraProfile>(`/halls/${hallId}/camera-profiles`):Promise.resolve([]),hallId);
 const selected=halls.data?.find(h=>h.id===hallId);const geometry=snapshot?.id===hallId?snapshot:selected;
 const available=(halls.data??[]).filter(h=>!h.archived||h.id===hallId);
 const cameras=(profiles.data??[]).filter(p=>p.hall_id===hallId&&geometry&&p.pitch_length_m===geometry.pitch_length_m&&p.pitch_width_m===geometry.pitch_width_m);
 if(!halls.data)return <Loading error={halls.error} retry={halls.reload}/>;
 return <><Field label="Зал"><select required={required} value={hallId} onChange={e=>onChange(e.target.value,'')}><option value="">Выберите зал</option>{available.map(h=><option key={h.id} value={h.id}>{h.name} · {h.address}{h.archived?' · в архиве':''}</option>)}</select></Field><Field label="Профиль камеры"><select value={cameraId} disabled={!hallId||!profiles.data||!!profiles.error} onChange={e=>onChange(hallId,e.target.value)}><option value="">Будет выбран позже</option>{cameras.map(p=><option key={p.id} value={p.id}>{p.name} · версия {p.version} · {p.frame_width} × {p.frame_height} px</option>)}</select></Field>{profiles.error&&<Loading error={profiles.error} retry={profiles.reload}/>}<div className="hall-selection-note">{geometry&&<p className="muted">Поле: {geometry.pitch_length_m} × {geometry.pitch_width_m} м · {geometry.address}{snapshot?.id===hallId?' · данные сохранены в матче':''}</p>}{geometry&&<YandexMapsLink address={geometry.address}/>}<button type="button" onClick={()=>setCreating(true)}>Создать зал</button>{hallId&&<Link to={`/halls/${hallId}`} target="_blank" rel="noopener">Зал и профили камер ↗</Link>}<button type="button" onClick={()=>{halls.reload();profiles.reload()}}>Обновить залы и камеры</button></div>{creating&&<Modal title="Создать зал" onClose={()=>setCreating(false)}><div className="hall-inline-create"><HallEditor embedded draftScope="inline-match" onSaved={hall=>{halls.setData([...(halls.data??[]).filter(h=>h.id!==hall.id),hall]);onChange(hall.id,'');setCreating(false)}}/></div></Modal>}</>;
}
