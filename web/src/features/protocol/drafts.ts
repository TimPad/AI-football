import {useEffect,useState,useRef} from 'react';
export function useDraft<T>(key:string,initial:T,validate:(v:unknown)=>v is T){
 const [loaded]=useState(()=>{let raw:string|null=null;try{raw=localStorage.getItem(key);if(!raw)return {value:initial,raw:null,error:'',dirty:false,corrupt:false};const stored=JSON.parse(raw);if(raw.length>1000000||stored.version!==1||!validate(stored.value))throw Error();return {value:stored.value as T,raw:null,error:'',dirty:true,corrupt:false}}catch{return {value:initial,raw,error:raw?'Повреждён черновик ввода. Скачайте его перед очисткой.':'Локальная копия ввода недоступна. Скачайте ввод перед закрытием.',dirty:!!raw,corrupt:!!raw}}});
 const [error,setError]=useState(loaded.error);const [value,setValue]=useState<T>(loaded.value);const [dirty,setDirty]=useState(loaded.dirty);const [raw,setRaw]=useState(loaded.raw);const [corrupt,setCorrupt]=useState(loaded.corrupt);const current=useRef(value);
 function change(next:T){if(corrupt)return;current.current=next;setValue(next);setDirty(true);try{localStorage.setItem(key,JSON.stringify({version:1,value:next}));setError('')}catch{setError('Локальная копия ввода недоступна. Скачайте черновик перед закрытием.')}}
 function markSaved(saved:T){if(corrupt||JSON.stringify(saved)!==JSON.stringify(current.current))return;setDirty(false);try{localStorage.removeItem(key)}catch{}}
 function clear(){try{localStorage.removeItem(key);setError('');setRaw(null);setCorrupt(false)}catch{setError('Не удалось очистить локальный черновик');if(corrupt)return}current.current=initial;setValue(initial);setDirty(false)}
 useEffect(()=>{const before=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue=''}};window.addEventListener('beforeunload',before);return()=>window.removeEventListener('beforeunload',before)},[dirty]);
 useEffect(()=>{if(!dirty){current.current=initial;setValue(initial)}},[JSON.stringify(initial),dirty]);
 return {value,change,clear,markSaved,error,dirty,raw,corrupt};
}
