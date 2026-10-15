import {Link,Outlet} from 'react-router-dom';
import {ArrowUpRight} from 'lucide-react';
import './shell.css';

export function PublicShell(){
 return <div className="public-shell">
  <header className="public-header"><div className="public-header-inner">
   <Link className="app-logo" to="/"><b>AI</b> Football</Link>
   <nav aria-label="Навигация зрителя"><Link to="/">Турниры и матчи</Link><Link className="top-link" to="/tournaments">Кабинет организатора<ArrowUpRight/></Link></nav>
  </div></header>
  <main className="public-main"><Outlet/></main>
  <footer className="public-footer">AI Football · Матчи, расписание и трансляции</footer>
 </div>;
}
