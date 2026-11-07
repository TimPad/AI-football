import {createContext,useContext,useEffect,type ReactNode} from 'react';
import {Link} from 'react-router-dom';
import {Calendar,ChartColumn,Users,Settings,Trophy,Video,ListOrdered} from 'lucide-react';

// Страница задаёт контекст рейла (турнир), оболочка его показывает.
export const RailContext=createContext<(node:ReactNode)=>void>(()=>{});
export function useCabinetRail(node:ReactNode,deps:unknown[]){
 const set=useContext(RailContext);
 useEffect(()=>{set(node);return()=>set(null)},deps);
}

export const TOURNAMENT_TABS=['table','matches','teams','analysis','ratings','rules','info'] as const;
export type TournamentTab=typeof TOURNAMENT_TABS[number];
// Прежние ссылки разделов, которые вошли в другие: публикация видна в списке матчей, игроки — в заявках команд.
export const LEGACY_TOURNAMENT_TABS:Record<string,TournamentTab>={publication:'matches',players:'teams',halls:'matches'};
export function readTournamentTab(raw:string|null):TournamentTab{
 const value=LEGACY_TOURNAMENT_TABS[raw??'']??raw;
 return (TOURNAMENT_TABS as readonly string[]).includes(value??'')?value as TournamentTab:'matches';
}

// Разделы турнира; «Настройки» — регламент и сведения о турнире.
const ITEMS:{tab:TournamentTab;label:string;icon:ReactNode;analytics?:boolean;also?:TournamentTab[]}[]=[
 {tab:'table',label:'Таблица',icon:<ListOrdered/>},{tab:'matches',label:'Матчи',icon:<Calendar/>},{tab:'teams',label:'Команды',icon:<Users/>},
 {tab:'analysis',label:'Обработка',icon:<Video/>,analytics:true},{tab:'ratings',label:'Рейтинги',icon:<ChartColumn/>,analytics:true},{tab:'rules',label:'Настройки',icon:<Settings/>,also:['info']}];

export function TournamentRail({id,name,active,analytics}:{id:string;name:string;active:TournamentTab|null;analytics:boolean}){
 return <>
  <Link className="rail-tournament" to={`/tournaments/${id}`}><Trophy/><span>{name}</span></Link>
  {ITEMS.filter(item=>!item.analytics||analytics).map(item=><Link key={item.tab} to={`/tournaments/${id}?tab=${item.tab}`}
   aria-current={active===item.tab||(active&&item.also?.includes(active))?'page':undefined}>{item.icon}{item.label}</Link>)}
 </>;
}
