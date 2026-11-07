import type {PairView,StageView} from './api';
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

type Leg=PairView['legs'][number];
export const shortDate=(iso:string,timezone:string)=>new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',timeZone:timezone}).format(new Date(iso));
const longDate=(iso:string,timezone:string)=>new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',hour:'2-digit',minute:'2-digit',timeZone:timezone}).format(new Date(iso));

export function legStatus(leg:Leg){
 if(leg.annulled)return 'Аннулирован';
 if(leg.technical)return 'Тех. поражение';
 return leg.status==='live'?'Идёт':leg.status==='postponed'?'Перенесён':leg.status==='cancelled'?'Отменён':null;
}
export function pairTotals(pair:PairView){
 const scored=pair.legs.filter(l=>l.score&&!l.annulled);
 if(!scored.length)return null;
 return {home:scored.reduce((s,l)=>s+(l.score!.home??0),0),away:scored.reduce((s,l)=>s+(l.score!.away??0),0)};
}
// Одна фраза для экранного диктора: раунд, счёт, кто прошёл, ближайший матч.
export function pairSpeech(pair:PairView,timezone:string){
 const parts=[pair.label];const t=pairTotals(pair);
 parts.push(pair.bye?`${pair.home.label} проходит без матча`:t?`${pair.home.label} ${t.home}, ${pair.away.label} ${t.away}`:`${pair.home.label} — ${pair.away.label}`);
 const pens=pair.legs.at(-1)?.shootout;if(pens&&pens.home!=null)parts.push(`Пенальти ${pens.home}:${pens.away}`);
 if(pair.walkover)parts.push('Техническая победа');
 const winner=pair.winner?pair[pair.winner].label:null;
 if(winner&&pair.bracket)parts.push(`${winner} прошёл дальше`);
 const next=pair.legs.find(l=>!l.score&&!l.annulled);
 if(next&&!pair.bye){const name=pair.legs.length>1?`Матч ${next.leg}`:'Матч';parts.push(next.scheduled_at?`${name} — ${longDate(next.scheduled_at,timezone)}`:`${name}: дата не назначена`)}
 return parts.join('. ');
}
