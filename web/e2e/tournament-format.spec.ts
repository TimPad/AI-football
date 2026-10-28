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
 await expect(page.getByRole('article',{name:/^Полуфинал\. A1 — B2/})).toBeVisible();
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
 await expect(p.getByRole('article',{name:/^Полуфинал\. A1 — B2/})).toContainText('Дата не назначена');
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

// Поддержка сценариев ниже: жеребьёвка групп через API, чтобы проверять правку состава и снятие.
async function drawGroups(env:Awaited<ReturnType<typeof setup>>,template='groups_playoff',extra:Record<string,unknown>={}){
 const stages=(await env.call(`/tournaments/${env.t.id}/format`,{template,regulation_id:env.reg.id,request_id:crypto.randomUUID(),...extra})).stages;
 const entries=(await env.call(`/tournaments/${env.t.id}/entries`,undefined,'GET')).items.map((e:{id:string})=>e.id);
 const drawn=(await env.call(`/stages/${stages[0].id}/draw`,{method:template==='groups_playoff'?'snake':'seeded',seed:0,seeding:entries,expected_revision:0,request_id:crypto.randomUUID()})).stages;
 return {stages:drawn,entries};
}
async function scheduleFixture(env:Awaited<ReturnType<typeof setup>>,id:string){
 return env.call(`/fixtures/${id}/schedule`,{request_id:crypto.randomUUID(),scheduled_at:'2026-11-03T18:00:00+03:00',hall_id:env.hall.id});
}

test('подсказки формата: рекомендация, исправление числа групп и «Кто играет»',async({page})=>{
 await login(page);const env=await setup(page,7);
 await page.goto(`/tournaments/${env.t.id}/setup?step=format`);
 await expect(page.getByText('Рекомендуем')).toBeVisible();
 const groups=page.getByRole('group',{name:'Групп',exact:true});
 await expect(groups).toContainText('2');
 await page.getByRole('button',{name:'Увеличить: Групп'}).click();await page.getByRole('button',{name:'Увеличить: Групп'}).click();
 await expect(page.getByText('Для 4 групп нужно минимум 8 команд')).toBeVisible();
 await page.getByRole('button',{name:'Сделать 3 группы'}).click();
 await expect(groups).toContainText('3');
 await page.getByRole('button',{name:'Изменить',exact:true}).click();
 await page.getByRole('dialog').getByRole('checkbox',{name:env.names[6]}).uncheck();
 await expect(page.getByRole('dialog')).toContainText('Кто играет · 6 из 7');
 await page.getByRole('dialog').getByRole('button',{name:'Готово'}).click();
 await expect(page.getByText(/Команд:/)).toContainText('Команд: 6');
 await page.getByRole('button',{name:'Как выбрать формат'}).click();
 await expect(page.getByRole('dialog',{name:'Как выбрать формат'}).getByRole('term')).toHaveCount(5);
 await page.getByRole('dialog').getByRole('button',{name:'Готово'}).click();
});

test('до старта команду убирают из группы, после старта — снимают по правилу половины (ровно половина — технические поражения)',async({page})=>{
 await login(page);const env=await setup(page,8);
 const {stages}=await drawGroups(env);
 const groupB=(await env.call(`/tournaments/${env.t.id}/fixtures?unscheduled=true`,undefined,'GET')).items.find((f:{group_no:number})=>f.group_no===2);
 const kept=await scheduleFixture(env,groupB.id);
 await page.goto(`/tournaments/${env.t.id}?tab=table`);
 const victim=stages[0].draw.placement[0][0];const victimName=env.names[(await env.call(`/tournaments/${env.t.id}/entries`,undefined,'GET')).items.findIndex((e:{id:string})=>e.id===victim)];
 const roster=page.getByRole('region',{name:'Состав этапа'});
 await roster.getByRole('listitem').filter({hasText:victimName}).getByRole('button',{name:'Убрать'}).click();
 const sheet=page.getByRole('dialog',{name:`Убрать ${victimName} из этапа`});
 await expect(sheet).toContainText('Сохранятся 1 назначенный матч, 0 будут отменены.');
 await sheet.getByRole('button',{name:'Применить'}).click();
 await expect(page.getByRole('region',{name:'Группа A'}).getByRole('row')).toHaveCount(4);
 expect((await env.call(`/matches/${kept.id}`,undefined,'GET')).status).toBe('scheduled');
 // Старт: результат в группе A, затем снятие команды с 1 сыгранным матчем из 2.
 const groupA=(await env.call(`/tournaments/${env.t.id}/fixtures?unscheduled=true`,undefined,'GET')).items.filter((f:{group_no:number})=>f.group_no===1);
 const played=await scheduleFixture(env,groupA[0].id);await env.finish(played.id,1,0);
 const loser=played.away.team.name;
 await page.reload();
 await page.getByRole('region',{name:'Групповой этап'}).getByRole('button',{name:'Снять команду'}).click();
 const dialog=page.getByRole('dialog',{name:'Снять команду'});
 await dialog.getByLabel('Команда').selectOption({label:loser});
 await expect(dialog.getByRole('status')).toContainText('Сыграно 1 из 2. Сыгранные матчи останутся, 1 оставшийся будет засчитан соперникам как технические победы.');
 await expect(dialog.getByRole('button',{name:'Технические поражения · по правилу'})).toHaveAttribute('aria-pressed','true');
 await dialog.getByRole('button',{name:'Снять команду'}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 const rows=page.getByRole('region',{name:'Группа A'}).getByRole('row');
 await expect(rows.last()).toContainText(loser);await expect(rows.last()).toContainText('Снялась');
 await expect(page.getByText('Тех. поражение').first()).toBeVisible();
});

test('сетка на компьютере: линии между раундами, текущий раунд и путь команды',async({page,browser})=>{
 await login(page);const env=await setup(page,4);
 await drawGroups(env,'playoff');
 const pending=(await env.call(`/tournaments/${env.t.id}/fixtures?unscheduled=true`,undefined,'GET')).items;
 const first=await scheduleFixture(env,pending.find((f:{key:string})=>f.key==='U1-1').id);await env.finish(first.id,3,1);
 const second=await scheduleFixture(env,pending.find((f:{key:string})=>f.key==='U1-2').id);await env.finish(second.id,0,2);
 const guest=await browser.newContext({viewport:{width:1440,height:900}});const p=await guest.newPage();
 await p.goto(`/watch/tournaments/${env.t.id}`);
 await expect(p.locator('.bracket-lines path')).toHaveCount(2);
 const semi=p.getByRole('article',{name:/^Полуфинал\. /}).first();
 await expect(semi).toContainText('3 : 1');
 await expect(semi.getByRole('link')).toHaveAttribute('href',`/watch/matches/${first.id}`);
 await p.getByRole('button',{name:first.home.team.name}).first().click();
 await expect(p.locator('.pair-card[data-path]')).toHaveCount(2);
 await p.keyboard.press('Escape');
 await expect(p.locator('.pair-card[data-path]')).toHaveCount(0);
 expect(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await p.screenshot({path:'test-results/bracket-1440.png'});
 await p.setViewportSize({width:375,height:812});await p.reload();
 await expect(p.getByRole('tab',{name:'Финал',exact:true})).toHaveAttribute('aria-selected','true');
 await p.screenshot({path:'test-results/bracket-375.png',fullPage:true});
 await p.getByRole('tab',{name:'Полуфинал'}).click();
 await expect(p.getByRole('tab',{name:'Полуфинал'})).toHaveAttribute('aria-selected','true');
 await expect(p.getByRole('tabpanel',{name:'Полуфинал'}).getByRole('article').first()).toBeInViewport();
 await p.waitForTimeout(400);await expect(p.getByRole('tab',{name:'Полуфинал'})).toHaveAttribute('aria-selected','true');
 await p.screenshot({path:'test-results/bracket-375-semis.png',fullPage:true});
 // Свайп: пролистывание вбок переключает вкладку.
 await p.locator('.bracket-strip').evaluate(el=>el.scrollTo({left:el.clientWidth}));
 await expect(p.getByRole('tab',{name:'Финал',exact:true})).toHaveAttribute('aria-selected','true');
 expect(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await guest.close();
});
