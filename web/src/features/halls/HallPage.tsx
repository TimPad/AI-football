import {YandexMapsLink} from '../../components/YandexMapsLink';
import {useState,type FormEvent} from 'react';
import {Link,useNavigate,useParams} from 'react-router-dom';
import {MapPin,Plus} from 'lucide-react';
import {all,api,post,ApiError} from '../../api/client';
import type {Hall,CameraProfile} from '../../api/domain';
import {Field,ErrorBox,Loading,Empty,useLoad,downloadJson,Check} from '../../components/ui';
import {useAuth} from '../auth/Auth';
import {useDraft} from '../protocol/drafts';
import {FramePicker,landmarks,pointLabel,readImageSize,type Frame} from './FramePicker';

export function HallList(){
 const state=useLoad(()=>all<Hall>('/halls'),'halls');
 return <><div className="page-head"><div><h1>Залы</h1><p className="muted">Площадки для расписания и видеоаналитики</p></div><Link className="primary button" to="/halls/new"><Plus/>Создать зал</Link></div>{!state.data?<Loading error={state.error} retry={state.reload}/>:!state.data.length?<Empty>Добавьте первый зал, чтобы назначать его матчам.</Empty>:<div className="hall-cards">{state.data.map(h=><Link className="surface hall-card" key={h.id} to={`/halls/${h.id}`}><div className="row"><h2>{h.name}</h2>{h.archived&&<span className="muted">В архиве</span>}</div><p><MapPin size={16}/>{h.address}</p><strong>{h.pitch_length_m} × {h.pitch_width_m} м</strong><small className="muted">{h.surface||'Покрытие не указано'}</small></Link>)}</div>}</>;
}
export function HallPage(){const {id}=useParams();return <HallContent key={id??'new'} id={id}/>}
function HallContent({id}:{id?:string}){
 const navigate=useNavigate();const state=useLoad(()=>id?api<Hall>(`/halls/${id}`):Promise.resolve(null),id??'new');
 if(state.data===undefined)return <Loading error={state.error} retry={state.reload}/>;
 return <><HallEditor key={state.data?.revision??0} existing={state.data??undefined} onSaved={h=>{state.setData(h);if(!id)navigate(`/halls/${h.id}`,{replace:true})}}/>{state.data&&<CameraProfiles hall={state.data}/>}</>;
}
// Optional latitude/longitude keep already-sent legacy drafts safely retryable.
type HallDraft={request_id:string,expected_revision:number,attempted:boolean,name:string,address:string,pitch_length_m:string,pitch_width_m:string,ceiling_height_m:string,latitude?:string,longitude?:string,surface:string,description:string,archived:boolean};
function hallDraft(h?:Hall):HallDraft{return {request_id:crypto.randomUUID(),expected_revision:h?.revision??0,attempted:false,name:h?.name??'',address:h?.address??'',pitch_length_m:String(h?.pitch_length_m??''),pitch_width_m:String(h?.pitch_width_m??''),ceiling_height_m:String(h?.ceiling_height_m??''),surface:h?.surface??'',description:h?.description??'',archived:h?.archived??false}}
function validHall(v:unknown):v is HallDraft{const d=v as HallDraft;return !!d&&typeof d.request_id==='string'&&typeof d.expected_revision==='number'&&typeof d.attempted==='boolean'&&typeof d.archived==='boolean'&&['name','address','pitch_length_m','pitch_width_m','ceiling_height_m','surface','description'].every(k=>typeof d[k as keyof HallDraft]==='string')}
const optionalNumber=(value:string)=>value===''?null:Number(value);
function HallEditor({existing,onSaved}:{existing?:Hall,onSaved:(h:Hall)=>void}){
 const auth=useAuth();const [initial]=useState(()=>hallDraft(existing));const draft=useDraft(`aifootball:hall:${auth.session!.id}:${existing?.id??'new'}`,initial,validHall);const d=draft.value;
 const [busy,setBusy]=useState(false);const [error,setError]=useState<unknown>();const locked=busy||d.attempted||draft.corrupt;
 function change(patch:Partial<HallDraft>){draft.change({...d,...patch,request_id:crypto.randomUUID()})}
 async function save(e:FormEvent){e.preventDefault();setBusy(true);setError(undefined);const submitted={...d,attempted:true};if(!d.attempted){delete submitted.latitude;delete submitted.longitude}draft.change(submitted);const body={request_id:d.request_id,name:d.name,address:d.address,pitch_length_m:Number(d.pitch_length_m),pitch_width_m:Number(d.pitch_width_m),ceiling_height_m:optionalNumber(d.ceiling_height_m),...(d.attempted&&d.latitude!==undefined&&d.longitude!==undefined?{latitude:optionalNumber(d.latitude),longitude:optionalNumber(d.longitude)}:{}),surface:d.surface,description:d.description};try{const h=existing?await api<Hall>(`/halls/${existing.id}`,{method:'PUT',body:JSON.stringify({...body,expected_revision:d.expected_revision,archived:d.archived})}):await post<Hall>('/halls',body);draft.clear();onSaved(h)}catch(e){setError(e);if(!(e instanceof ApiError)||(e.code!=='network'&&e.status<500))draft.change({...d,attempted:false,request_id:crypto.randomUUID()})}finally{setBusy(false)}}
 return <><Link className="breadcrumb" to="/halls">Залы / {existing?'Карточка зала':'Новый зал'}</Link><div className="page-head"><div><h1>{existing?existing.name:'Создать зал'}</h1><p className="muted">Укажите размеры игровой площадки между линиями разметки.</p></div></div>{draft.dirty&&<p className="draft-banner">Ввод сохранён в черновике</p>}{draft.error&&<p className="error">{draft.error}</p>}{d.attempted&&!busy&&<p className="warning">Ответ на сохранение не получен. Повторная отправка не создаст второй зал.</p>}
 <form onSubmit={save} className="surface"><fieldset className="team-fieldset" disabled={locked}><div className="form-grid"><Field label="Название зала"><input required maxLength={200} value={d.name} onChange={e=>change({name:e.target.value})}/></Field><Field label="Адрес зала"><input required maxLength={1000} value={d.address} onChange={e=>change({address:e.target.value})}/></Field>{([['pitch_length_m','Длина поля, м',true,300],['pitch_width_m','Ширина поля, м',true,300],['ceiling_height_m','Высота потолка, м',false,100]] as const).map(([key,label,required,max])=><Field key={key} label={label}><input type="number" required={required} min="0.01" max={max} step="any" value={d[key]} onChange={e=>change({[key]:e.target.value})}/></Field>)}<Field label="Покрытие"><input maxLength={200} placeholder="Паркет, резина, искусственная трава" value={d.surface} onChange={e=>change({surface:e.target.value})}/></Field></div><p className="muted">Адрес и размеры вводит администратор. Укажите город, улицу и номер здания.</p><YandexMapsLink address={d.address}/><Field label="Описание зала"><textarea rows={3} maxLength={4000} value={d.description} onChange={e=>change({description:e.target.value})}/></Field>{existing&&<Check label="Зал в архиве" checked={d.archived} onChange={archived=>change({archived})}/>}</fieldset><ErrorBox error={error}/>{error instanceof ApiError&&error.status===409&&<button type="button" onClick={()=>{draft.clear();window.location.reload()}}>Отбросить ввод и обновить с сервера</button>}<div className="team-save-bar"><button className="primary" disabled={busy||draft.corrupt}>{busy?'Сохраняем…':d.attempted?'Повторить сохранение':'Сохранить зал'}</button><button type="button" onClick={()=>downloadJson(d,'зал-черновик.json')}>Скачать ввод</button></div>{existing&&<p className="muted">Матчи сохраняют выбранные размеры. Правка карточки зала применяется к новым назначениям.</p>}</form></>;
}
type Point={px:[string,string],m:[string,string]};
type CameraDraft={request_id:string,expected_hall_revision:number,attempted:boolean,name:string,frame_width:string,frame_height:string,points:Point[],polygon:string,calibration:string};
function cameraDraft(h:Hall):CameraDraft{return {request_id:crypto.randomUUID(),expected_hall_revision:h.revision,attempted:false,name:'Основная камера',frame_width:'',frame_height:'',points:[[0,0],[h.pitch_length_m,0],[h.pitch_length_m,h.pitch_width_m],[0,h.pitch_width_m]].map(m=>({px:['',''],m:m.map(String) as [string,string]})),polygon:'',calibration:''}}
function validCamera(v:unknown):v is CameraDraft{const d=v as CameraDraft;return !!d&&typeof d.request_id==='string'&&typeof d.expected_hall_revision==='number'&&typeof d.attempted==='boolean'&&['name','frame_width','frame_height','polygon','calibration'].every(k=>typeof d[k as keyof CameraDraft]==='string')&&Array.isArray(d.points)&&d.points.length>=4&&d.points.every(p=>p&&Array.isArray(p.px)&&Array.isArray(p.m)&&p.px.length===2&&p.m.length===2&&[...p.px,...p.m].every(x=>typeof x==='string'))}
function CameraProfiles({hall}:{hall:Hall}){
 const state=useLoad(()=>all<CameraProfile>(`/halls/${hall.id}/camera-profiles`),`${hall.id}:${hall.revision}`);const [open,setOpen]=useState(false);
 return <section className="surface hall-profiles"><div className="panel-head"><div><h2>Камеры и координаты поля</h2><p className="muted">Для неподвижной камеры: точки на кадре → метры на поле.</p></div><button disabled={hall.archived} onClick={()=>setOpen(!open)}>{open?'Закрыть форму':'Добавить профиль камеры'}</button></div>{open&&<CameraEditor key={hall.revision} hall={hall} onSaved={()=>{state.reload();setOpen(false)}}/>}{!state.data?<Loading error={state.error} retry={state.reload}/>:!state.data.length?<p className="muted">Профиль ещё не добавлен. Для назначения зала в расписании он не требуется.</p>:<div className="camera-versions">{state.data.map(p=><details key={p.id}><summary>{p.name} · версия {p.version}{!p.matches_current_dimensions?' · прежние размеры поля':''}</summary><p className="muted">Кадр {p.frame_width} × {p.frame_height} · поле {metres(p.pitch_length_m)} × {metres(p.pitch_width_m)} м · точность разметки около {cm(p.reprojection_error_m)} см{p.leave_one_out_error_m!=null?` (проверка — ${cm(p.leave_one_out_error_m)} см)`:''}</p><ReferenceFrame hall={hall} profile={p} onSaved={state.reload}/><ProfilePoints points={p.points}/></details>)}</div>}</section>;
}
const metres=(v:number)=>v.toLocaleString('ru-RU',{maximumFractionDigits:2});
const cm=(m:number)=>Math.max(1,Math.round(m*100));
// Опорные точки — свёрнутой таблицей: номер совпадает с подписью точки на эталонном кадре.
function ProfilePoints({points}:{points:CameraProfile['points']}){
 return <details className="profile-points"><summary>Опорные точки · {points.length}</summary><table><thead><tr><th>№</th><th>На кадре, px</th><th>На поле, м</th></tr></thead>
  <tbody>{(points as {px:number[];m:number[]}[]).map((pt,i)=><tr key={i} className="num"><td>{i+1}</td><td>{pt.px.map(v=>Math.round(v)).join(' × ')}</td><td>{pt.m.map(metres).join(' × ')}</td></tr>)}</tbody></table></details>;
}
// Эталонный кадр версии профиля: обработчик сверяет с ним положение камеры в каждой записи
// и сам поправляет небольшой сдвиг. Точки и контур рисуются поверх — видно, легли ли они на разметку.
function ReferenceFrame({hall,profile,onSaved}:{hall:Hall;profile:CameraProfile;onSaved:()=>void}){
 const [busy,setBusy]=useState(false);const [error,setError]=useState<unknown>();
 const path=`/halls/${hall.id}/camera-profiles/${profile.id}/reference-frame`;
 async function upload(file:File){setBusy(true);setError(undefined);try{const body=new FormData();body.set('file',file);await api<CameraProfile>(path,{method:'PUT',body,signal:AbortSignal.timeout(120000)});onSaved()}catch(e){setError(e)}finally{setBusy(false)}}
 const w=profile.frame_width,h=profile.frame_height;
 if(profile.reference_sha256)return <figure className="reference-frame">
  <div className="reference-stage" style={{aspectRatio:`${w} / ${h}`}}>
   <img src={`/api/v1${path}`} alt={`Эталонный кадр камеры «${profile.name}», версия ${profile.version}`}/>
   <svg viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
    <polygon points={profile.pitch_polygon_px.map(p=>p.join(',')).join(' ')} strokeWidth={w/250}/>
    {(profile.points as {px:[number,number]}[]).map((p,i)=><g key={i}><circle cx={p.px[0]} cy={p.px[1]} r={w/180}/><text x={p.px[0]+w/120} y={p.px[1]-w/150} fontSize={w/45}>{i+1}</text></g>)}
   </svg>
  </div>
  <figcaption className="muted">Эталонный кадр. В каждой записи обработчик сверяет с ним положение камеры и сам поправляет небольшой сдвиг; при большом — попросит новую версию профиля. Точки и контур нанесены по профилю и должны лежать на разметке поля.</figcaption>
 </figure>;
 return <div className="reference-upload">
  <p>Эталонный кадр не загружен. Загрузите кадр этой камеры в том же положении и разрешении ({w} × {h} px), по которому отмечены точки: обработчик будет сам замечать сдвиг камеры между днями и поправлять геометрию.</p>
  <label className={`button${busy?' disabled':''}`}>{busy?'Загружаем…':'Загрузить эталонный кадр'}<input type="file" accept="image/jpeg,image/png,image/webp" hidden disabled={busy||hall.archived} onChange={e=>{const f=e.target.files?.[0];if(f)upload(f);e.target.value=''}}/></label>
  <ErrorBox error={error}/>
  <p className="muted small">Кадр задаётся один раз для версии профиля. Задания, выданные до загрузки, создайте заново.</p>
 </div>;
}
function CameraEditor({hall,onSaved}:{hall:Hall,onSaved:()=>void}){
 const auth=useAuth();const [initial]=useState(()=>cameraDraft(hall));const draft=useDraft(`aifootball:camera:${auth.session!.id}:${hall.id}:${hall.revision}`,initial,validCamera);const d=draft.value;const [busy,setBusy]=useState(false);const [error,setError]=useState<unknown>();const locked=busy||d.attempted||draft.corrupt;
 // Кадр живёт только в браузере до сохранения: после создания профиля он же загружается как эталонный.
 const [frame,setFrame]=useState<Frame|null>(null);const [chosen,setChosen]=useState<number|null>(null);
 const marks=landmarks(hall.pitch_length_m,hall.pitch_width_m);
 const empty=(p:Point)=>p.px[0]===''||p.px[1]==='';
 // Активная точка — выбранная вручную или первая неотмеченная; когда отмечены все, клик по кадру ничего не меняет.
 const active=chosen??d.points.findIndex(empty);
 function change(patch:Partial<CameraDraft>){draft.change({...d,...patch,request_id:crypto.randomUUID()})}
 async function openFrame(file:File){setError(undefined);try{const {url,w,h}=await readImageSize(file);if(frame)URL.revokeObjectURL(frame.url);setFrame({file,url,w,h});change({frame_width:String(w),frame_height:String(h)});setChosen(null)}catch(e){setError(e)}}
 function pick(px:[number,number]){const points=d.points.map((p,n)=>n===active?{...p,px:px.map(String) as [string,string]}:p);change({points});
  // Следующей становится первая ещё не отмеченная точка.
  const next=points.findIndex(empty);setChosen(next<0?null:next)}
 function addLandmark(index:number){const m=marks[index];if(!m)return;change({points:[...d.points,{px:['',''],m:m.m.map(String) as [string,string]}]});setChosen(d.points.length)}
 async function save(e:FormEvent){e.preventDefault();setError(undefined);
  const missing=d.points.map((p,i)=>empty(p)||p.m[0]===''||p.m[1]===''?i+1:0).filter(Boolean);
  if(!d.frame_width||!d.frame_height){setError(new Error('Загрузите кадр с камеры или укажите размер кадра'));return}
  if(missing.length){setError(new Error(`Отметьте на кадре точки: ${missing.join(', ')}`));return}
  setBusy(true);try{const points=d.points.map(p=>({px:p.px.map(Number),m:p.m.map(Number)}));const body={request_id:d.request_id,expected_hall_revision:d.expected_hall_revision,name:d.name,frame_width:Number(d.frame_width),frame_height:Number(d.frame_height),points,pitch_polygon_px:d.polygon.trim()?JSON.parse(d.polygon):points.slice(0,4).map(p=>p.px),calibration:d.calibration.trim()?JSON.parse(d.calibration):null};draft.change({...d,attempted:true});const profile=await post<CameraProfile>(`/halls/${hall.id}/camera-profiles`,body);draft.clear();
   // Тот же кадр — эталонный для сверки сдвига камеры; ошибка загрузки не отменяет созданный профиль.
   if(frame){try{const form=new FormData();form.set('file',frame.file);await api<CameraProfile>(`/halls/${hall.id}/camera-profiles/${profile.id}/reference-frame`,{method:'PUT',body:form,signal:AbortSignal.timeout(120000)})}catch{/* кадр можно загрузить в карточке профиля */}}
   onSaved()}catch(e){setError(e);if(!(e instanceof ApiError)||(e.code!=='network'&&e.status<500))draft.change({...d,attempted:false,request_id:crypto.randomUUID()})}finally{setBusy(false)}}
 const table=<><div className="team-table-scroll"><table className="camera-point-table"><thead><tr><th>Точка</th><th>X кадра, px</th><th>Y кадра, px</th><th>X поля, м</th><th>Y поля, м</th><th/></tr></thead><tbody>{d.points.map((p,i)=><tr key={i}><th>{i+1}</th>{(['px','m'] as const).flatMap(kind=>[0,1].map(axis=><td key={`${kind}:${axis}`}><input aria-label={`Точка ${i+1}: ${axis?'Y':'X'} ${kind==='px'?'кадра':'поля'}`} type="number" step="any" min={0} max={kind==='px'?Number(axis?d.frame_height:d.frame_width)-1:axis?hall.pitch_width_m:hall.pitch_length_m} value={p[kind][axis]} onChange={e=>change({points:d.points.map((point,n)=>n===i?{...point,[kind]:point[kind].map((v,a)=>a===axis?e.target.value:v) as [string,string]}:point)})}/></td>))}<td>{i>=4&&<button type="button" aria-label={`Убрать точку ${i+1}`} onClick={()=>{change({points:d.points.filter((_,n)=>n!==i)});setChosen(null)}}>×</button>}</td></tr>)}</tbody></table></div><button type="button" disabled={d.points.length>=50} onClick={()=>change({points:[...d.points,{px:['',''],m:['','']}]})}>Добавить опорную точку</button></>;
 return <form className="camera-editor" onSubmit={save} noValidate>{draft.error&&<p className="error">{draft.error}</p>}{d.attempted&&!busy&&<p className="warning">Повторите сохранение, чтобы получить ответ для того же профиля.</p>}<fieldset className="team-fieldset" disabled={locked}>
  <Field label="Название камеры"><input required maxLength={200} value={d.name} onChange={e=>change({name:e.target.value})}/></Field>
  <h3>Кадр с камеры</h3>
  <p className="muted">Стоп-кадр записи этой камеры в том разрешении, которое будет обрабатываться. Размер кадра определится сам, а после сохранения кадр станет эталонным — по нему обработчик заметит сдвиг камеры.</p>
  <label className={`button${frame?'':' primary'}`}>{frame?'Заменить кадр':'Загрузить кадр'}<input type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={e=>{const f=e.target.files?.[0];if(f)void openFrame(f);e.target.value=''}}/></label>
  {frame?<>
   <p className="frame-step" role="status">{active<0?'Все точки отмечены. Чтобы поправить точку, выберите её номер ниже.':<>Отметьте точку {active+1}: <b>{pointLabel(d.points[active],marks,active)}</b> — кликните по этому месту на кадре.</>}</p>
   <FramePicker frame={frame} points={d.points} active={active} disabled={locked||active<0} onPick={pick}/>
   <div className="frame-points">{d.points.map((p,i)=><button type="button" key={i} aria-pressed={i===active} className={empty(p)?'':'done'} onClick={()=>setChosen(i)} title={pointLabel(p,marks,i)}>{i+1}{empty(p)?'':' ✓'}</button>)}
    <select aria-label="Добавить точку разметки" value="" onChange={e=>addLandmark(Number(e.target.value))}><option value="">+ точка разметки…</option>{marks.map((m,i)=><option key={i} value={i}>{m.label}</option>)}</select></div>
   <p className="muted small">Первые четыре точки — углы поля, по ним строится контур. Чем больше видимых точек разметки, тем точнее координаты. Кадр {frame.w} × {frame.h} px.</p>
   <details className="camera-advanced"><summary>Координаты точек числами</summary>{table}</details>
  </>:<>
   <div className="form-grid"><Field label="Ширина кадра, px"><input type="number" min={16} max={16384} value={d.frame_width} onChange={e=>change({frame_width:e.target.value})}/></Field><Field label="Высота кадра, px"><input type="number" min={16} max={16384} value={d.frame_height} onChange={e=>change({frame_height:e.target.value})}/></Field></div>
   <details className="camera-advanced"><summary>Ввести координаты точек числами</summary><p className="muted">Первые четыре точки — углы поля по порядку обхода. Ось X идёт вдоль длины ({hall.pitch_length_m} м), Y — вдоль ширины ({hall.pitch_width_m} м). На кадре X направлен вправо, Y вниз.</p>{table}</details>
  </>}
  <details className="camera-advanced"><summary>Область поля и коррекция объектива</summary><Field label="Контур поля на кадре, JSON"><textarea rows={3} value={d.polygon} onChange={e=>change({polygon:e.target.value})} placeholder="[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]"/></Field><p className="muted">Если оставить пустым, контур проходит через первые четыре точки. При невидимых углах задайте видимый контур отдельно и используйте известные точки разметки.</p><Field label="Калибровка объектива, JSON"><textarea rows={3} value={d.calibration} onChange={e=>change({calibration:e.target.value})} placeholder={'{"K":[[fx,0,cx],[0,fy,cy],[0,0,1]],"dist":[k1,k2,p1,p2,k3]}'}/></Field></details></fieldset><ErrorBox error={error}/><div className="team-save-bar"><button className="primary" disabled={busy||draft.corrupt}>{d.attempted?'Повторить сохранение профиля':'Сохранить профиль камеры'}</button></div><p className="muted">При перемещении камеры, зуме или смене разрешения создайте новую версию профиля.</p></form>;
}

