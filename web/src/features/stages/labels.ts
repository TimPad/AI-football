import type {StageView} from './api';
const CRITERIA:Record<string,string>={points:'очки',h2h_points:'личные встречи',h2h_goal_diff:'разница в личных встречах',h2h_goals:'голы в личных встречах',
 goal_diff:'разница мячей',goals_for:'забитые',wins:'победы',buchholz:'очки соперников',lot:'жребий'};
// Личные встречи в подписи одной фразой: очки, разница и голы в них идут подряд.
export function criteriaText(criteria:string[]){
 const words:string[]=[];for(const c of criteria){const w=c.startsWith('h2h_')?CRITERIA.h2h_points:CRITERIA[c]??c;if(words[words.length-1]!==w)words.push(w)}
 return `Места: ${words.join(' → ')}`;
}
export const KIND:Record<StageView['kind'],string>={round_robin:'Каждый с каждым',groups:'Группы',single_elim:'Плей-офф',double_elim:'Двойное выбывание',swiss:'Швейцарская система'};
export const STATUS:Record<StageView['status'],string>={draft:'Нужна жеребьёвка',drawn:'Жеребьёвка проведена',started:'Идёт',completed:'Завершён'};
