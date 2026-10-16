import {createContext,useContext,useEffect,useState,type ReactNode,type FormEvent} from 'react';
import {useLocation,Navigate} from 'react-router-dom';
import {api,post,setCsrf} from '../../api/client';
import type {Session} from '../../api/domain';
import {ErrorBox,Field} from '../../components/ui';
type AuthState={session:Session|null,loading:boolean,loggedOut:boolean,login:(name:string,password:string)=>Promise<void>,logout:()=>Promise<void>};
const Context=createContext<AuthState|null>(null);
export const useAuth=()=>useContext(Context)!;
export function AuthProvider({children}:{children:ReactNode}){
 const [session,setSession]=useState<Session|null>(null);const [loading,setLoading]=useState(true);
 // Явный выход не запоминает страницу: следующий вход (возможно, другого человека) начинается со списка турниров.
 const [loggedOut,setLoggedOut]=useState(false);
 const assign=(s:Session|null)=>{setSession(s);setCsrf(s?.csrf_token??'')};
 useEffect(()=>{api<Session>('/auth/me').then(assign).catch(()=>assign(null)).finally(()=>setLoading(false));const expired=()=>assign(null);window.addEventListener('session-expired',expired);return()=>window.removeEventListener('session-expired',expired)},[]);
 return <Context.Provider value={{session,loading,loggedOut,login:async(name,password)=>{assign(await post<Session>('/auth/login',{login:name,password}));setLoggedOut(false)},logout:async()=>{await post('/auth/logout',{});setLoggedOut(true);assign(null)}}}>{children}</Context.Provider>
}
export function Private({children}:{children:ReactNode}){const {session,loading,loggedOut}=useAuth();const location=useLocation();return loading?<p className="empty">Проверяем сессию…</p>:session?children:<Navigate to="/login" state={loggedOut?null:{from:location.pathname}} replace/>}
export function Login(){
 const {session,login}=useAuth();const location=useLocation();const [error,setError]=useState<unknown>();const [busy,setBusy]=useState(false);
 if(session)return <Navigate replace to={location.state?.from??'/tournaments'}/>;
 async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const f=new FormData(e.currentTarget);setBusy(true);setError(undefined);try{await login(String(f.get('login')),String(f.get('password')))}catch(e){setError(e)}finally{setBusy(false)}}
 return <main className="login"><div className="login-brand">AI <b>Football</b></div><form className="surface" onSubmit={submit}><h1>Кабинет организатора</h1><p className="muted">Турниры, команды и протоколы матчей</p><Field label="Логин"><input name="login" autoComplete="username" required autoFocus/></Field><Field label="Пароль"><input name="password" type="password" autoComplete="current-password" required/></Field><ErrorBox error={error}/><button className="primary" disabled={busy}>{busy?'Входим…':'Войти'}</button></form></main>
}
