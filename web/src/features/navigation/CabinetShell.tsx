import {useEffect,useRef,useState,type ReactNode} from 'react';
import {RailContext} from './rail';
import {NavLink,Outlet,useLocation} from 'react-router-dom';
import {Trophy,Users,UserRound,MapPin,LogOut,Menu,X,ExternalLink,BookOpen,ChevronDown} from 'lucide-react';
import {useAuth} from '../auth/Auth';
import './shell.css';

// Вверху — «Турниры» и меню «Справочники»; боковое меню есть только внутри турнира (его разделы).
// Так «Команды» турнира и справочник команд не стоят рядом с одинаковыми названиями.
// Ниже 1024px всё уходит в выдвижную панель: сначала разделы турнира, затем справочники.
const CATALOG=[{to:'/teams',label:'Команды',icon:<Users/>},{to:'/players',label:'Игроки',icon:<UserRound/>},{to:'/halls',label:'Залы',icon:<MapPin/>}];

function CatalogMenu(){
 const [open,setOpen]=useState(false);const location=useLocation();const box=useRef<HTMLDivElement>(null);
 useEffect(()=>setOpen(false),[location.pathname]);
 useEffect(()=>{
  if(!open)return;
  const outside=(e:MouseEvent)=>{if(!box.current?.contains(e.target as Node))setOpen(false)};
  const escape=(e:KeyboardEvent)=>{if(e.key==='Escape')setOpen(false)};
  document.addEventListener('mousedown',outside);document.addEventListener('keydown',escape);
  return()=>{document.removeEventListener('mousedown',outside);document.removeEventListener('keydown',escape)};
 },[open]);
 const here=CATALOG.some(c=>location.pathname.startsWith(c.to));
 return <div className="catalog-menu" ref={box}>
  <button className={`catalog-toggle${here?' active':''}`} aria-expanded={open} onClick={()=>setOpen(!open)}><BookOpen/>Справочники<ChevronDown/></button>
  {open&&<div className="catalog-list">{CATALOG.map(c=><NavLink key={c.to} to={c.to}>{c.icon}{c.label}</NavLink>)}</div>}
 </div>;
}

export function CabinetShell(){
 const auth=useAuth();const location=useLocation();const [open,setOpen]=useState(false);const [rail,setRail]=useState<ReactNode>(null);
 useEffect(()=>setOpen(false),[location.pathname]);
 return <div className={`cabinet${rail?'':' no-rail'}`}>
  <header className="cabinet-top">
   <button className="icon-button cabinet-menu" onClick={()=>setOpen(!open)} aria-label="Меню" aria-expanded={open}>{open?<X/>:<Menu/>}</button>
   <NavLink className="app-logo" to="/tournaments"><b>AI</b> Football</NavLink>
   <nav className="cabinet-global" aria-label="Кабинет"><NavLink to="/tournaments" end><Trophy/>Турниры</NavLink><CatalogMenu/></nav>
   <div className="cabinet-top-right">
    <NavLink to="/" className="top-link"><ExternalLink/>Открыть сайт</NavLink>
    <span className="cabinet-user"><UserRound/><span><b>{auth.session?.login}</b><small>{auth.session?.can_manage_analytics?'Админ+':'Администратор'}</small></span></span>
    <button className="icon-button" onClick={()=>void auth.logout()} aria-label="Выйти"><LogOut/></button>
   </div>
  </header>
  {open&&<div className="cabinet-shade" onClick={()=>setOpen(false)}/>}
  <nav className={`cabinet-rail${open?' open':''}`} aria-label={rail?'Турнир':'Меню'}>
   {rail}
   <div className="rail-global"><NavLink to="/tournaments" end><Trophy/>Все турниры</NavLink>
    <h4>Справочники</h4>{CATALOG.map(c=><NavLink key={c.to} to={c.to}>{c.icon}{c.label}</NavLink>)}</div>
  </nav>
  <main className="cabinet-main"><RailContext.Provider value={setRail}><Outlet/></RailContext.Provider></main>
 </div>;
}
