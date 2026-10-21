import {MapPin} from 'lucide-react';
export function YandexMapsLink({address,latitude,longitude}:{address:string,latitude?:number|null,longitude?:number|null}){
 const query=address.trim();
 if(!query)return null;
 const params=latitude!=null&&longitude!=null?new URLSearchParams({ll:`${longitude},${latitude}`,pt:`${longitude},${latitude},pm2gnm`,z:'16'}):`text=${encodeURIComponent(query)}`;
 return <a className="yandex-map-link" href={`https://yandex.ru/maps/?${params}`} target="_blank" rel="noopener noreferrer"><MapPin size={16}/>Открыть в Яндекс Картах</a>;
}
