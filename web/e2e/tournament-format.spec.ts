import {test,expect,type Page} from '@playwright/test';
import {login} from './helpers';

// Подготовка через API (команды, регламент, зал), формат и жеребьёвка — через интерфейс.
async function setup(page:Page,teams:number){
 const session=await (await page.request.get('/api/v1/auth/me')).json();const headers={'X-CSRF-Token':session.csrf_token,Origin:new URL(page.url()).origin};
 async function call(path:string,data?:unknown,method='POST'){const r=await page.request.fetch(`/api/v1${path}`,{method,data,headers});expect(r.ok(),await r.text()).toBeTruthy();return r.json()}
 const suffix=crypto.randomUUID().slice(0,6);
 const t=await call('/tournaments',{name:`Кубок формата ${suffix}`,season:'2026',starts_on:'2026-11-01',ends_on:'2026-12-31',timezone:'Europe/Moscow',visibility:'public'});
 const preset=(await call('/tournaments/regulation-presets',undefined,'GET')).items[0].rules;
 const reg=await call(`/tournaments/${t.id}/regulations`,{variant_name:'Основной',rules:preset});
 const names:string[]=[];
 for(let i=1;i<=teams;i++){const name=`Команда ${i} ${suffix}`;names.push(name);const team=await call('/teams',{name});await call(`/tournaments/${t.id}/entries`,{team_id:team.id})}
 const hall=await call('/halls',{name:`Зал ${suffix}`,address:'Ярославль, Спортивная, 1',pitch_length_m:40,pitch_width_m:20});
 async function finish(matchId:string,home:number,away:number){
  let m=await call(`/matches/${matchId}`,undefined,'GET');
  const send=async(kind:string,payload:unknown)=>{m=await call(`/matches/${matchId}/commands`,{request_id:crypto.randomUUID(),expected_revision:m.revision,kind,payload});return m};
  await send('set_totals',{reported_totals:{home:{score:home},away:{score:away}}});await send('set_status',{status:'ended'});await send('confirm',{acknowledge_incomplete:true});
  const version=(await call(`/matches/${matchId}/versions`,undefined,'GET')).items[0];await send('publish',{version_id:version.id});
 }
 return {t,reg,names,hall,call,finish};
}

test('организатор выбирает формат и проводит жеребьёвку, зритель видит таблицу и сетку на телефоне',async({page,browser})=>{
 await login(page);const env=await setup(page,8);
 await page.goto(`/tournaments/${env.t.id}/setup?step=format`);
 await expect(page.getByRole('radio',{name:/Группы и плей-офф/})).toHaveAttribute('aria-checked','true');
 await page.getByRole('button',{name:'Сохранить формат',exact:true}).click();
 await expect(page.getByText('Сейчас: Групповой этап → Плей-офф')).toBeVisible();
 await page.getByRole('link',{name:'4. Жеребьёвка'}).click();
 // Групповой этап: по корзинам, обмен двух команд, подтверждение.
 await page.getByRole('region',{name:'Групповой этап'}).getByRole('button',{name:'Провести жеребьёвку',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await dialog.getByRole('button',{name:'Провести жеребьёвку',exact:true}).click();
 await expect(dialog.getByRole('heading',{name:'Группа A'})).toBeVisible();
 const first=dialog.locator('.draw-group').nth(0).locator('.draw-team').first();const second=dialog.locator('.draw-group').nth(1).locator('.draw-team').first();
 const [a,b]=[await first.textContent(),await second.textContent()];
 await first.click();await second.click();
 await expect(dialog.locator('.draw-group').nth(0).locator('.draw-team').first()).toHaveText(b!);
 await dialog.getByRole('button',{name:'Подтвердить жеребьёвку',exact:true}).click();
 await expect(page.getByRole('region',{name:'Группа A'})).toBeVisible();
 await expect(page.getByRole('region',{name:'Группа B'}).getByRole('button',{name:a!})).toBeVisible();
 // Плей-офф: по схеме из групп.
 await page.getByRole('region',{name:'Плей-офф'}).getByRole('button',{name:'Провести жеребьёвку',exact:true}).click();
 await dialog.getByRole('button',{name:'Провести жеребьёвку',exact:true}).click();
 await expect(dialog.getByRole('button',{name:'1. A1'})).toBeVisible();
 await dialog.getByRole('button',{name:'Подтвердить жеребьёвку',exact:true}).click();
 await expect(page.getByRole('article',{name:'Полуфинал: A1 — B2'})).toBeVisible();
 // Назначение пары без даты.
 await page.goto(`/tournaments/${env.t.id}?tab=matches`);
 const unscheduled=page.getByRole('region',{name:'Без даты'});
 await expect(unscheduled.getByText('Соперник ещё не известен').first()).toBeVisible();
 await unscheduled.getByRole('button',{name:'Назначить',exact:true}).first().click();
 await page.getByRole('dialog').getByLabel('Зал',{exact:true}).selectOption({label:`${env.hall.name} · ${env.hall.address}`});
 await page.getByRole('dialog').getByRole('button',{name:'Назначить матч',exact:true}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 const matches=(await env.call(`/tournaments/${env.t.id}/matches`,undefined,'GET')).items;
 expect(matches).toHaveLength(1);expect(matches[0].stage_label).toMatch(/^Группа A · Тур 1/);
 await env.finish(matches[0].id,2,0);
 // Зритель на 375 px: таблица открыта первой, победитель с 3 очками, сетка с подписями, без горизонтальной прокрутки.
 const guest=await browser.newContext({viewport:{width:375,height:812}});const p=await guest.newPage();
 await p.goto(`/watch/tournaments/${env.t.id}`);
 const groupA=p.getByRole('region',{name:'Группа A'});
 await expect(groupA.getByRole('row').nth(1)).toContainText('3');
 await expect(groupA.getByRole('row').nth(1)).toContainText(matches[0].home.team.name);
 await expect(p.getByRole('tab',{name:'Полуфинал'})).toBeVisible();
 await expect(p.getByRole('article',{name:'Полуфинал: A1 — B2'})).toContainText('Дата не назначена');
 expect(await p.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
 await groupA.getByRole('button',{name:matches[0].home.team.name}).click();
 await expect(groupA.getByText(/В 1 · Н 0 · П 0 · Мячи 2:0/)).toBeVisible();
 await p.getByRole('navigation',{name:'Разделы турнира'}).getByRole('link',{name:'Матчи',exact:true}).click();
 await expect(p.getByRole('region',{name:'Ещё без даты'})).toBeVisible();
 expect(await p.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
 await guest.close();
});

test('турнир без формата показывает общую таблицу',async({page,browser})=>{
 await login(page);const env=await setup(page,2);
 const entries=(await env.call(`/tournaments/${env.t.id}/entries`,undefined,'GET')).items;
 const match=await env.call(`/tournaments/${env.t.id}/matches`,{home_entry_id:entries[0].id,away_entry_id:entries[1].id,regulation_id:env.reg.id,scheduled_at:'2026-11-02T18:00:00+03:00',hall_id:env.hall.id});
 await env.finish(match.id,1,1);
 const guest=await browser.newContext({viewport:{width:375,height:812}});const p=await guest.newPage();
 await p.goto(`/watch/tournaments/${env.t.id}`);
 await p.getByRole('navigation',{name:'Разделы турнира'}).getByRole('link',{name:'Таблица',exact:true}).click();
 const table=p.getByRole('region',{name:'Турнирная таблица'});
 await expect(table.getByRole('row')).toHaveCount(3);
 await expect(table.getByRole('row').nth(1)).toContainText('1');
 expect(await p.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
 await guest.close();
});
