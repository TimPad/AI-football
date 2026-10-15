import {useEffect,useState,type ReactNode} from 'react';
import {RailContext} from './rail';
import {NavLink,Outlet,useLocation} from 'react-router-dom';
import {Trophy,Users,UserRound,MapPin,LogOut,Menu,X,ExternalLink} from 'lucide-react';
import {useAuth} from '../auth/Auth';
import './shell.css';

// Рейл 224px вне ширины рабочей области; ниже 1024px — выдвижная панель.
export function CabinetShell(){
 const auth=useAuth();const location=useLocation();const [open,setOpen]=useState(false);const [rail,setRail]=useState<ReactNode>(null);
 useEffect(()=>setOpen(false),[location.pathname]);
 return <div className="cabinet">
  <header className="cabinet-top">
   <button className="icon-button cabinet-menu" onClick={()=>setOpen(!open)} aria-label="Меню" aria-expanded={open}>{open?<X/>:<Menu/>}</button>
   <NavLink className="app-logo" to="/tournaments"><b>AI</b> Football</NavLink>
   <div className="cabinet-top-right">
    <NavLink to="/" className="top-link"><ExternalLink/>Открыть сайт</NavLink>
    <span className="cabinet-user"><UserRound/><span><b>{auth.session?.login}</b><small>{auth.session?.can_manage_analytics?'Админ+':'Администратор'}</small></span></span>
    <button className="icon-button" onClick={()=>void auth.logout()} aria-label="Выйти"><LogOut/></button>
   </div>
  </header>
  {open&&<div className="cabinet-shade" onClick={()=>setOpen(false)}/>}
  <nav className={`cabinet-rail${open?' open':''}`} aria-label="Кабинет">
   {rail}
   <h4>{rail?'Справочники':'Кабинет'}</h4>
   <NavLink to="/tournaments" end><Trophy/>{rail?'Все турниры':'Турниры'}</NavLink>
   <NavLink to="/teams"><Users/>{rail?'Все команды':'Команды'}</NavLink>
   <NavLink to="/players"><UserRound/>{rail?'Все игроки':'Игроки'}</NavLink>
   <NavLink to="/halls"><MapPin/>{rail?'Все залы':'Залы'}</NavLink>
  </nav>
  <main className="cabinet-main"><RailContext.Provider value={setRail}><Outlet/></RailContext.Provider></main>
 </div>;
}
