import {useQueryPatch} from '../navigation/useQueryPatch';
import {VideoAnalysisTab} from './AnalysisTab';

// Рабочее место проверки: версия, вид задачи, трек и фильтр — в URL задачи матча.
export function ReviewWorkspace({matchId,actorId,canManage}:{matchId:string;actorId:string;canManage:boolean}){
 const [params,update]=useQueryPatch();
 return <VideoAnalysisTab matchId={matchId} actorId={actorId} canManage={canManage} nav={{params,update}}/>;
}
