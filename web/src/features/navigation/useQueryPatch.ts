import {useCallback,useRef} from 'react';
import {useSearchParams} from 'react-router-dom';
import {patchQuery} from './query';

// Роутер применяет навигацию в переходе: до перерисовки второе изменение
// получило бы старые параметры и стёрло первое. Копим ещё не отрисованные правки.
export function useQueryPatch():[URLSearchParams,(patch:Record<string,string|null>,options?:{replace?:boolean})=>void]{
 const [params,setParams]=useSearchParams();
 const pending=useRef<URLSearchParams|null>(null);
 if(pending.current&&pending.current.toString()===params.toString())pending.current=null;
 const update=useCallback((patch:Record<string,string|null>,options:{replace?:boolean}={})=>{
  const next=patchQuery(pending.current??params,patch);pending.current=next;setParams(next,options);
 },[params,setParams]);
 return [params,update];
}
