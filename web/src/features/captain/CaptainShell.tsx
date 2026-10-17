import {Link,Outlet,useNavigate,useLocation} from 'react-router-dom';
import {useCaptainAuth} from './CaptainAuth';
import {useLoad} from '../../components/ui';
import {api} from '../../api/client';
import type {TeamProfile} from '../../api/domain';
import './captain.css';
export function CaptainShell(){const {session,logout}=useCaptainAuth();const navigate=useNavigate();const location=useLocation();const teams=useLoad(()=>api<{items:TeamProfile[]}>('/captain/teams'),location.pathname);
 return <div className="captain-shell"><header><Link className="app-logo" to="/">AI Football</Link><Link to="/captain">Кабинет команды</Link>{(teams.data?.items.length??0)>0&&<select aria-label="Моя команда" value={teams.data!.items.find(t=>location.pathname.includes(t.id))?.id??''} onChange={e=>{if(e.target.value)navigate(`/captain/teams/${e.target.value}`)}}><option value="">Выберите команду</option>{teams.data!.items.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select>}<span>{session!.display_name}</span><button onClick={()=>void logout()}>Выйти</button></header><main><Outlet/></main></div>;
}
