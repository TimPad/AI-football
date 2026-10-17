// Одно поле трансляции ВК: обычная ссылка, адрес плеера (video_ext.php) или весь код <iframe>.
// Из кода встраивания получаем и плеер для сайта, и обычную ссылку на видео.
export type Broadcast={broadcast_url:string|null;broadcast_embed_url:string|null};
const HOST=/^(www\.)?(vk\.com|vkvideo\.ru)$/;

export function parseBroadcast(input:string):Broadcast|{error:string}{
 const text=input.trim();
 if(!text)return {broadcast_url:null,broadcast_embed_url:null};
 const src=/<iframe[^>]*\ssrc=["']([^"']+)["']/i.exec(text)?.[1]?.replace(/&amp;/g,'&');
 let url:URL;
 try{url=new URL(src??text)}catch{return {error:'Вставьте ссылку на видео ВК или код встраивания'}}
 if(url.protocol!=='https:'||!HOST.test(url.hostname)||url.username||url.password)return {error:'Нужна ссылка на ВК или VK Видео, начинающаяся с https://'};
 if(url.pathname==='/video_ext.php'){
  const oid=url.searchParams.get('oid')??'',id=url.searchParams.get('id')??'';
  if(!/^-?\d+$/.test(oid)||!/^\d+$/.test(id))return {error:'В адресе плеера ВК нет номера видео (oid и id)'};
  return {broadcast_url:`https://vk.com/video${oid}_${id}`,broadcast_embed_url:url.toString()};
 }
 return {broadcast_url:url.toString(),broadcast_embed_url:null};
}

// В поле показываем то, что даёт больше: плеер, если он есть, иначе ссылку.
export const broadcastValue=(url?:string|null,embed?:string|null)=>embed||url||'';
