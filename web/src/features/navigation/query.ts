// Адресуемое состояние интерфейса: раздел, издание, игрок, фильтры. Не уровень вкладок.
export const PUBLIC_MATCH_TABS=['overview','events','players','stats','video'] as const;
export const PRIVATE_MATCH_TABS=['overview','lineup','protocol','review','participation','actions','report','publication','info','history'] as const;
const LEGACY_PRIVATE:Record<string,string>={analysis:'review',video:'review'};

export function readMatchTab(params:URLSearchParams,audience:'public'|'private'):string{
 const tab=params.get('tab')??'';
 if(audience==='public')return (PUBLIC_MATCH_TABS as readonly string[]).includes(tab)?tab:'overview';
 const value=LEGACY_PRIVATE[tab]??tab;
 return (PRIVATE_MATCH_TABS as readonly string[]).includes(value)?value:'overview';
}

export function patchQuery(current:URLSearchParams,patch:Record<string,string|null>):URLSearchParams{
 const next=new URLSearchParams(current);
 for(const [key,value] of Object.entries(patch)){if(value===null)next.delete(key);else next.set(key,value);}
 return next;
}

const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function isUuid(value:string|null):boolean{return value!==null&&UUID.test(value)}
