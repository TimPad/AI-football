import {useEffect,useState} from 'react';
import {api} from '../../../api/client';
export function useMedia(query:string){const [match,setMatch]=useState(()=>window.matchMedia?.(query).matches??false);useEffect(()=>{const media=window.matchMedia?.(query);if(!media)return;const change=()=>setMatch(media.matches);change();media.addEventListener('change',change);return()=>media.removeEventListener('change',change)},[query]);return match}
export const useWideScreen=()=>useMedia('(min-width:1200px)');
export const useNarrowScreen=()=>useMedia('(max-width:760px)');
// A refresh of the same path keeps the shown data until the new answer arrives, so lists do not blink into «Загружаем…».
export function usePublicRequest<T>(path:string,tick=0):{data?:T,error?:unknown}{
 const key=`${path}|${tick}`;const [state,setState]=useState<{key:string,path:string,data?:T,error?:unknown}>({key:'',path:''});
 useEffect(()=>{const controller=new AbortController();api<T>(path,{signal:controller.signal}).then(data=>{if(!controller.signal.aborted)setState({key,path,data})}).catch(error=>{if(!controller.signal.aborted)setState(old=>({key,path,error,data:old.path===path?old.data:undefined}))});return()=>controller.abort()},[key]);
 if(state.key===key)return state;
 return state.path===path&&state.data!==undefined?{data:state.data}:{};
}
