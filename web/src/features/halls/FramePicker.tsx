import type {MouseEvent} from 'react';

export type Frame={file:File;url:string;w:number;h:number};
export type PickPoint={px:[string,string];m:[string,string]};
export type Landmark={label:string;m:[number,number]};

// Точки разметки мини-футбольного поля в метрах: X — вдоль длины, Y — вдоль ширины.
// Отметки 6 и 10 м и ворота 3 м — по правилам футзала; линии поля берутся из карточки зала.
export function landmarks(length:number,width:number):Landmark[]{
 const L=length,W=width,c=W/2,r=(v:number)=>Math.round(v*100)/100;
 const at=(x:number,y:number)=>`${r(x).toLocaleString('ru-RU')} × ${r(y).toLocaleString('ru-RU')} м`;
 const list:[string,number,number][]=[
  ['Угол',0,0],['Угол',L,0],['Угол',L,W],['Угол',0,W],
  ['Центральная линия, край',L/2,0],['Центральная линия, край',L/2,W],['Центр поля',L/2,c],
  ['Отметка 6 м',6,c],['Отметка 6 м',L-6,c],['Отметка 10 м',10,c],['Отметка 10 м',L-10,c],
  ['Штанга ворот',0,c-1.5],['Штанга ворот',0,c+1.5],['Штанга ворот',L,c-1.5],['Штанга ворот',L,c+1.5],
 ];
 return list.map(([name,x,y])=>({label:`${name} · ${at(x,y)}`,m:[r(x),r(y)]}));
}

export function pointLabel(p:PickPoint,marks:Landmark[],i:number){
 const m=p.m.map(Number);
 return marks.find(l=>Math.abs(l.m[0]-m[0])<0.01&&Math.abs(l.m[1]-m[1])<0.01)?.label??`Точка ${i+1} · ${p.m.join(' × ')} м`;
}

// Размер кадра — из самого изображения: так точки и эталонный кадр заведомо в одном разрешении.
export function readImageSize(file:File):Promise<{url:string;w:number;h:number}>{
 return new Promise((resolve,reject)=>{
  const url=URL.createObjectURL(file);const img=new Image();
  img.onload=()=>resolve({url,w:img.naturalWidth,h:img.naturalHeight});
  img.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('Не удалось открыть изображение'))};
  img.src=url;
 });
}

// Кадр с наложенными точками: клик ставит пиксель активной точки.
export function FramePicker({frame,points,active,disabled,onPick}:{frame:Frame;points:PickPoint[];active:number;disabled:boolean;onPick:(px:[number,number])=>void}){
 const {w,h}=frame;
 const placed=points.map((p,i)=>({i,x:Number(p.px[0]),y:Number(p.px[1]),set:p.px[0]!==''&&p.px[1]!==''}));
 const corners=placed.slice(0,4).filter(p=>p.set);
 function pick(e:MouseEvent<SVGSVGElement>){
  if(disabled)return;const box=e.currentTarget.getBoundingClientRect();
  const x=Math.round((e.clientX-box.left)/box.width*w),y=Math.round((e.clientY-box.top)/box.height*h);
  onPick([Math.min(w-1,Math.max(0,x)),Math.min(h-1,Math.max(0,y))]);
 }
 return <div className="reference-stage frame-picker" style={{aspectRatio:`${w} / ${h}`}}>
  <img src={frame.url} alt="Кадр с камеры для разметки"/>
  <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Разметка точек на кадре" onClick={pick} style={{cursor:disabled?'default':'crosshair'}}>
   {corners.length>1&&<polygon points={corners.map(p=>`${p.x},${p.y}`).join(' ')} strokeWidth={w/250}/>}
   {placed.filter(p=>p.set).map(p=><g key={p.i} className={p.i===active?'active':''}><circle cx={p.x} cy={p.y} r={w/(p.i===active?120:180)}/><text x={p.x+w/120} y={p.y-w/150} fontSize={w/45}>{p.i+1}</text></g>)}
  </svg>
 </div>;
}
