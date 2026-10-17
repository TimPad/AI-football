import {Field} from '../../components/ui';
import {broadcastValue,parseBroadcast,type Broadcast} from './vk';

export function BroadcastFields({url,embed}:{url?:string|null,embed?:string|null}){
 return <><Field label="Трансляция ВК"><input name="broadcast" maxLength={4000} placeholder="Ссылка на видео или код встраивания" defaultValue={broadcastValue(url,embed)}/></Field>
  <p className="muted broadcast-help">Чтобы видео играло прямо на сайте, вставьте код встраивания из ВК («Поделиться» → «Код для вставки»). Обычная ссылка откроет видео в ВК.</p></>;
}

// Поле формы → два поля API; ошибка разбора — до отправки.
export function readBroadcast(f:FormData):Broadcast{
 const parsed=parseBroadcast(String(f.get('broadcast')??''));
 if('error' in parsed)throw new Error(parsed.error);
 return parsed;
}
