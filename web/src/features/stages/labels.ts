import type {StageView} from './api';
export const CRITERIA:Record<string,string>={points:'очки',h2h_points:'личные встречи',h2h_goal_diff:'разница в личных встречах',h2h_goals:'голы в личных встречах',
 goal_diff:'разница мячей',goals_for:'забитые',wins:'победы',buchholz:'очки соперников',lot:'жребий'};
// Личные встречи в подписи одной фразой: очки, разница и голы в них идут подряд.
export function criteriaText(criteria:string[]){
 const words:string[]=[];for(const c of criteria){const w=c.startsWith('h2h_')?CRITERIA.h2h_points:CRITERIA[c]??c;if(words[words.length-1]!==w)words.push(w)}
 return `Места: ${words.join(' → ')}`;
}
export const KIND:Record<StageView['kind'],string>={round_robin:'Каждый с каждым',groups:'Группы',single_elim:'Плей-офф',double_elim:'Двойное выбывание',swiss:'Швейцарская система'};
export const STATUS:Record<StageView['status'],string>={draft:'Нужна жеребьёвка',drawn:'Жеребьёвка проведена',started:'Идёт',completed:'Завершён'};

export function plural(n:number,one:string,few:string,many:string){const t=n%100;if(t>=11&&t<=14)return many;const d=n%10;return d===1?one:d>=2&&d<=4?few:many}

export const TEMPLATE_NAME:Record<string,string>={league:'Лига',groups_playoff:'Группы и плей-офф',playoff:'Плей-офф',double_elim:'Двойное выбывание',swiss:'Швейцарская система'};
export const TEMPLATE_HINT:Record<string,string>={league:'Каждый с каждым, места по очкам',groups_playoff:'Группы, затем сетка на выбывание',playoff:'Сетка на выбывание с первого матча',
 double_elim:'Выбывают после двух поражений',swiss:'Соперники по очкам, без повторов'};
export const FORMAT_GUIDE:Record<string,{fits:string;pros:string;cons:string}>={
 league:{fits:'До 8 команд и много игровых дней',pros:'Самый честный итог: каждый с каждым',cons:'Матчей много: при 12 командах — 66'},
 groups_playoff:{fits:'От 8 до 32 команд',pros:'Все играют минимум 3 матча, в конце — решающие игры',cons:'Нужно согласовать группы и сетку'},
 playoff:{fits:'Мало игровых дней',pros:'Быстро: турнир на 8 команд — за 3 дня',cons:'Проигравшие выбывают после первого матча'},
 double_elim:{fits:'От 4 до 16 команд',pros:'Одна неудача не выбивает из турнира',cons:'Сложнее понять зрителям'},
 swiss:{fits:'Много команд и мало дней',pros:'Соперники равной силы, все играют одинаково',cons:'Незнакомо многим игрокам'},
};
