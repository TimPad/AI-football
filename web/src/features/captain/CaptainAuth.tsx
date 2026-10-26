import {createContext,useContext,useEffect,useState,useRef,type ReactNode,type FormEvent} from 'react';
import {useDocumentTitle} from '../../components/useDocumentTitle';
import {Link,Navigate,useLocation} from 'react-router-dom';
import {api,post,setCsrf,ApiError} from '../../api/client';
import type {components} from '../../api/types';
import {ErrorBox,Field} from '../../components/ui';
import {useDraft} from '../protocol/drafts';
type Session=components['schemas']['CaptainSessionView'];
type Auth={session:Session|null,loading:boolean,login:(email:string,password:string)=>Promise<void>,logout:()=>Promise<void>};
const Context=createContext<Auth|null>(null);
export const useCaptainAuth=()=>useContext(Context)!;
export function CaptainAuthProvider({children}:{children:ReactNode}){
 const [session,setSession]=useState<Session|null>(null);const [loading,setLoading]=useState(true);
 const generation=useRef(0);
 function assign(value:Session|null){setSession(value);setCsrf(value?.csrf_token??'','captain')}
 useEffect(()=>{const version=generation.current;api<Session>('/captain/auth/me').then(value=>{if(generation.current===version)assign(value)}).catch(()=>{if(generation.current===version)assign(null)}).finally(()=>{if(generation.current===version)setLoading(false)});const expired=(event:Event)=>{if((event as CustomEvent).detail?.audience!=='admin'){generation.current++;assign(null)}};window.addEventListener('session-expired',expired);return()=>{generation.current++;window.removeEventListener('session-expired',expired)}},[]);
 return <Context.Provider value={{session,loading,login:async(email,password)=>{const version=++generation.current;const result=await post<Session>('/captain/auth/login',{email,password});if(version===generation.current){assign(result);setLoading(false)}},logout:async()=>{generation.current++;await post('/captain/auth/logout',{});assign(null)}}}>{children}</Context.Provider>;
}
export function CaptainPrivate({children}:{children:ReactNode}){const {session,loading}=useCaptainAuth();const l=useLocation();return loading?<p className="empty">Проверяем сессию команды…</p>:session?children:<Navigate replace to="/captain/login" state={{from:l.pathname+l.search+l.hash}}/>}
function destination(value:unknown){return typeof value==='string'&&/^\/captain(?:\/|$)/.test(value)&&!value.startsWith('/captain/login')?value:'/captain'}
export function CaptainLogin(){const auth=useCaptainAuth();const location=useLocation();const [error,setError]=useState<unknown>();const [busy,setBusy]=useState(false);
 useDocumentTitle('Вход капитана');
 if(auth.session)return <Navigate replace to={destination(location.state?.from)}/>;
 async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);setError(undefined);const f=new FormData(e.currentTarget);try{await auth.login(String(f.get('email')),String(f.get('password')))}catch(e){setError(e)}finally{setBusy(false)}}
 return <main className="login"><Link className="login-brand" to="/"><b>AI</b> Football</Link><form className="surface" onSubmit={submit}><h1>Кабинет команды</h1><p className="muted">Состав, заявки и проверка игроков вашей команды</p><Field label="Email"><input type="email" name="email" autoComplete="username" required/></Field><Field label="Пароль"><input type="password" name="password" autoComplete="current-password" required/></Field><ErrorBox error={error}/><button className="primary" disabled={busy}>Войти</button><p><Link to="/captain/register" state={location.state}>Зарегистрироваться капитаном</Link></p><Link to="/captain/password-reset">Забыли пароль?</Link></form></main>;
}
export function CaptainRegister(){const [busy,setBusy]=useState(false);const [error,setError]=useState<unknown>();const [sent,setSent]=useState(false);const [requestId]=useState(()=>crypto.randomUUID());
 async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);setError(undefined);const f=new FormData(e.currentTarget);try{await post('/captain/auth/register',{...Object.fromEntries(f),request_id:requestId});setSent(true)}catch(e){setError(e)}finally{setBusy(false)}}
 return <main className="login"><Link className="login-brand" to="/"><b>AI</b> Football</Link>{sent?<section className="surface"><h1>Проверьте почту</h1><p>Откройте ссылку из письма, подтвердите email и войдите. После этого можно создать команду.</p><Link to="/captain/login">Перейти ко входу</Link></section>:<form className="surface" onSubmit={submit}><h1>Регистрация капитана</h1><p className="muted">Контакты доступны организатору и не публикуются.</p><Field label="Имя капитана"><input name="display_name" maxLength={200} autoComplete="name" required/></Field><Field label="Email"><input name="email" type="email" autoComplete="email" required/></Field><Field label="Пароль"><input name="password" type="password" minLength={12} maxLength={200} autoComplete="new-password" required/></Field><p className="muted small">Не менее 12 символов</p><ErrorBox error={error}/><button className="primary" disabled={busy}>Зарегистрироваться</button><p><Link to="/captain/login">Уже есть аккаунт</Link></p></form>}</main>;
}
function tokenKey(token:string){return Array.from(token).reduce((h,c)=>(h*31+c.charCodeAt(0))>>>0,0).toString(16)}
export function CaptainTokenPage({kind}:{kind:'verify'|'reset'|'invitation'}){
 const location=useLocation();const auth=useCaptainAuth();const token=new URLSearchParams(location.hash.slice(1)).get('token')??'';
 const [initial]=useState(()=>({request_id:crypto.randomUUID(),pending:false}));const draft=useDraft(`aifootball:captain-token:${kind}:${tokenKey(token)}`,initial,(v:unknown):v is typeof initial=>!!v&&typeof v==='object'&&'request_id' in v&&typeof v.request_id==='string'&&'pending' in v);
 const [email,setEmail]=useState('');const [password,setPassword]=useState('');const [message,setMessage]=useState('');const [error,setError]=useState<unknown>();const [busy,setBusy]=useState(false);
 async function submit(e:FormEvent){e.preventDefault();setBusy(true);setError(undefined);const pending={...draft.value,pending:true};draft.change(pending);
  try{if(kind==='reset'&&!token){await post('/captain/auth/password-reset',{email});setMessage('Если адрес подходит для восстановления, на него будет отправлено письмо.')}
   else{const path=kind==='invitation'?'/captain/invitations/accept':kind==='verify'?'/captain/auth/verify':'/captain/auth/password-reset/complete';await post(path,{token,request_id:pending.request_id,...(kind==='reset'?{password}:{})});setMessage(kind==='invitation'?'Доступ к команде получен':kind==='verify'?'Email подтверждён':'Пароль обновлён')}
   draft.clear();setPassword('');
  }catch(e){setError(e);if(e instanceof ApiError&&e.status>0&&e.status<500)draft.change({...pending,pending:false})}finally{setBusy(false)}
 }
 if(kind==='invitation'&&!auth.loading&&!auth.session)return <Navigate replace to="/captain/login" state={{from:location.pathname+location.hash}}/>;
 return <main className="login"><Link className="login-brand" to="/"><b>AI</b> Football</Link><section className="surface"><h1>{message||({verify:'Подтвердите email',reset:'Восстановление доступа',invitation:'Приглашение в команду'}[kind])}</h1>{message?<p><Link to={kind==='invitation'?'/captain':'/captain/login'}>{kind==='invitation'?'К своей команде':'Войти в кабинет команды'}</Link></p>:<form onSubmit={submit}>
  {kind==='reset'&&!token?<Field label="Email"><input type="email" required value={email} onChange={e=>setEmail(e.target.value)}/></Field>:kind==='reset'?<Field label="Новый пароль"><input type="password" required minLength={12} maxLength={200} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}/></Field>:<p>{token?'Нажмите кнопку, чтобы продолжить.':'В ссылке нет кода. Откройте полную ссылку из письма.'}</p>}
  <ErrorBox error={error}/><button className="primary" disabled={busy||draft.corrupt||(!token&&kind!=='reset')}>{busy?'Сохраняем…':draft.value.pending?'Повторить отправку':kind==='invitation'?'Принять приглашение':kind==='verify'?'Подтвердить email':token?'Обновить пароль':'Отправить ссылку'}</button>
 </form>}</section></main>;
}
