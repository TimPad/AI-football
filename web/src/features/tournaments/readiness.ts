export function protocolPublicationState(m:{published_version_id:string|null;latest_confirmed_version_id?:string|null}){
 if(m.published_version_id)return m.latest_confirmed_version_id&&m.latest_confirmed_version_id!==m.published_version_id?'new_version':'published';
 return m.latest_confirmed_version_id?'ready':'draft';
}
