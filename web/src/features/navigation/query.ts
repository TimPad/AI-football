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

export function scheduleReturn(value:unknown,tournamentId:string):string{
 const path=`/tournaments/${tournamentId}`,fallback=path+'?tab=matches';
 if(typeof value!=='string'||value.length>2000||!value.startsWith('/')||value.startsWith('//'))return fallback;
 try{const url=new URL(value,'https://local.invalid');if(url.origin!=='https://local.invalid'||url.pathname!==path)return fallback;const params=new URLSearchParams({tab:'matches'});for(const key of ['day','hall_id','status','view','team_id','attention']){const v=url.searchParams.get(key);if(v)params.set(key,v)}return path+'?'+params.toString()}catch{return fallback}
}
