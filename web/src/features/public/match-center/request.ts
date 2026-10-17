import {useEffect,useState} from 'react';
import {api} from '../../../api/client';
export function useWideScreen(){const [wide,setWide]=useState(()=>window.matchMedia?.('(min-width:1200px)').matches??false);useEffect(()=>{const media=window.matchMedia?.('(min-width:1200px)');if(!media)return;const change=()=>setWide(media.matches);media.addEventListener('change',change);return()=>media.removeEventListener('change',change)},[]);return wide}
export function usePublicRequest<T>(path:string,tick=0){
 const key=`${path}|${tick}`;const [state,setState]=useState<{key:string,data?:T,error?:unknown}>({key:''});
 useEffect(()=>{const controller=new AbortController();api<T>(path,{signal:controller.signal}).then(data=>{if(!controller.signal.aborted)setState({key,data})}).catch(error=>{if(!controller.signal.aborted)setState({key,error})});return()=>controller.abort()},[key]);
 return state.key===key?state:{key};
}
