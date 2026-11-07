import {useEffect,useRef,useState} from 'react';
import {Link,NavLink,Outlet,useLocation} from 'react-router-dom';
import {ChevronDown} from 'lucide-react';
import './shell.css';

export function PublicShell(){
 return <div className="public-shell">
  <header className="public-header"><div className="public-header-inner">
   <Link className="app-logo" to="/"><b>AI</b> Football</Link>
   <nav aria-label="Навигация зрителя"><NavLink to="/" end>Матчи</NavLink><NavLink to="/watch/tournaments">Турниры</NavLink><SignInMenu/></nav>
  </div></header>
  <main className="public-main"><Outlet/></main>
  <footer className="public-footer">AI Football · Матчи, расписание и трансляции</footer>
 </div>;
}

// One entry for both cabinets: the guest picks a role, not a page with its own login.
function SignInMenu(){
 const [open,setOpen]=useState(false);const box=useRef<HTMLDivElement>(null);const {pathname}=useLocation();
 useEffect(()=>setOpen(false),[pathname]);
 useEffect(()=>{if(!open)return;
  const outside=(e:PointerEvent)=>{if(!box.current?.contains(e.target as Node))setOpen(false)};
  const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){setOpen(false);box.current?.querySelector('button')?.focus()}};
  document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);
  return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)};
 },[open]);
 return <div className="signin" ref={box}><button type="button" className="signin-button" aria-expanded={open} aria-controls="signin-menu" onClick={()=>setOpen(v=>!v)}>Войти<ChevronDown aria-hidden="true"/></button>
  {open&&<div id="signin-menu" className="signin-menu" role="group" aria-label="Войти как">
   <Link to="/captain"><b>Капитан команды</b><small>Состав, заявки и проверка игроков</small></Link>
   <Link to="/tournaments"><b>Организатор</b><small>Турниры, протоколы и публикация</small></Link>
  </div>}
 </div>;
}
