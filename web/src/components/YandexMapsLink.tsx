import {MapPin} from 'lucide-react';
export function YandexMapsLink({address}:{address:string}){
 const query=address.trim();
 if(!query)return null;
 return <a className="yandex-map-link" href={`https://yandex.ru/maps/?text=${encodeURIComponent(query)}`} target="_blank" rel="noopener noreferrer"><MapPin size={16}/>Открыть в Яндекс Картах</a>;
}
