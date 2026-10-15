import {createContext,useContext,useEffect,type ReactNode} from 'react';
import {Link} from 'react-router-dom';
import {Calendar,ChartColumn,Upload,Users,UserRound,MapPin,FileText,Info,Trophy} from 'lucide-react';

// Страница задаёт контекст рейла (турнир), оболочка его показывает.
export const RailContext=createContext<(node:ReactNode)=>void>(()=>{});
export function useCabinetRail(node:ReactNode,deps:unknown[]){
 const set=useContext(RailContext);
 useEffect(()=>{set(node);return()=>set(null)},deps);
}

export const TOURNAMENT_TABS=['matches','ratings','publication','teams','players','halls','rules','info'] as const;
export type TournamentTab=typeof TOURNAMENT_TABS[number];
const GROUPS:{title:string;items:{tab:TournamentTab;label:string;icon:ReactNode;analytics?:boolean}[]}[]=[
 {title:'Работа',items:[{tab:'matches',label:'Матчи',icon:<Calendar/>},{tab:'ratings',label:'Рейтинги',icon:<ChartColumn/>,analytics:true},{tab:'publication',label:'Публикация',icon:<Upload/>}]},
 {title:'Участники и площадки',items:[{tab:'teams',label:'Команды',icon:<Users/>},{tab:'players',label:'Игроки',icon:<UserRound/>},{tab:'halls',label:'Залы',icon:<MapPin/>}]},
 {title:'Настройки',items:[{tab:'rules',label:'Регламент',icon:<FileText/>},{tab:'info',label:'Сведения',icon:<Info/>}]},
];

export function TournamentRail({id,name,active,analytics}:{id:string;name:string;active:TournamentTab|null;analytics:boolean}){
 return <>
  <Link className="rail-tournament" to={`/tournaments/${id}`}><Trophy/><span>{name}</span></Link>
  {GROUPS.map(group=><div key={group.title} className="rail-group"><h4>{group.title}</h4>
   {group.items.filter(item=>!item.analytics||analytics).map(item=><Link key={item.tab} to={`/tournaments/${id}?tab=${item.tab}`}
    aria-current={active===item.tab?'page':undefined}>{item.icon}{item.label}</Link>)}</div>)}
 </>;
}
