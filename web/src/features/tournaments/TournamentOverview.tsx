import {useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../../api/client';
import {ErrorBox} from '../../components/ui';
import type {Data} from './TournamentPage';
export function nextStep(d:Data){return d.t.archived?null:!d.rules.length?{label:'Настроить регламент',href:`/tournaments/${d.t.id}/setup?step=rules`}:d.entries.length<2?{label:'Добавить команды',href:`/tournaments/${d.t.id}/setup?step=teams`}:null}
export function TournamentOverview({data:d,onSaved}:{data:Data,onSaved:()=>void}){
 const [busy,setBusy]=useState(false);const [error,setError]=useState<unknown>();const next=nextStep(d);
 async function publish(){setBusy(true);setError(undefined);try{await api(`/tournaments/${d.t.id}`,{method:'PATCH',body:JSON.stringify({expected_revision:d.t.revision,visibility:d.t.visibility==='public'?'draft':'public'})});onSaved()}catch(e){setError(e)}finally{setBusy(false)}}
 return <section className="surface tournament-readiness"><div className="row wrap"><b>{d.t.visibility==='public'?'Страница опубликована':'Черновик турнира'}</b><span className="muted">Команд: {d.entries.length} · Матчей: {d.matches.length} · {d.rules.length?'Регламент сохранён':'Нет регламента'}</span>
  {next&&<Link className="button primary" to={next.href}>{next.label}</Link>}{!d.t.archived&&<button disabled={busy} onClick={publish}>{d.t.visibility==='public'?'Скрыть страницу':'Опубликовать страницу турнира'}</button>}</div><p className="muted small">Результаты матчей, видеоаналитика и рейтинги публикуются отдельно в своих разделах.</p><ErrorBox error={error}/></section>;
}
