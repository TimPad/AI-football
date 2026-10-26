import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {login,createTournament} from './helpers';

test('calendar groups, preserved return, empty day and responsive layout',async({page,browser})=>{
 await login(page);const first=await createTournament(page);await page.goto('/tournaments');const second=await createTournament(page);
 const guest=await browser.newContext();const p=await guest.newPage();await p.goto('/?day=2026-10-20');
 // Строки матчей рисуются вместе со списком: без ожидания count() видит пустую страницу, а «Ещё матчи» есть лишь при >50 матчах дня.
 await expect(p.getByRole('link',{name:/^Открыть матч /}).first()).toBeVisible();
 for(let n=0;n<100&&(!await p.getByRole('link',{name:`Открыть матч ${first.home} — ${first.away}`}).count()||!await p.getByRole('link',{name:`Открыть матч ${second.home} — ${second.away}`}).count());n++){await p.getByRole('button',{name:'Ещё матчи',exact:true}).click();await expect(p.getByRole('button',{name:'Загружаем…',exact:true})).toHaveCount(0)}
 await expect(p.getByRole('link',{name:`Открыть матч ${first.home} — ${first.away}`})).toBeVisible();await expect(p.getByRole('link',{name:`Открыть матч ${second.home} — ${second.away}`})).toBeVisible();
 await p.getByRole('link',{name:`Открыть матч ${first.home} — ${first.away}`} ).click();await p.getByRole('link',{name:'← К календарю матчей'}).click();await expect(p.getByLabel('Дата матчей')).toHaveValue('2026-10-20');
 await p.getByLabel('Дата матчей').fill('2020-01-01');await expect(p.getByText(/1 января матчей нет/)).toBeVisible();await expect(p.getByLabel('Дата матчей')).toHaveValue('2020-01-01');
 await p.getByLabel('Дата матчей').fill('2026-10-20');
 for(const width of [1440,1024,390]){await p.setViewportSize({width,height:900});await expect(p.getByRole('link',{name:`Открыть матч ${first.home} — ${first.away}`})).toBeVisible();expect(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await p.screenshot({path:`test-results/match-center-${width}.png`,fullPage:true})}
 // На телефоне турниры, статус и поиск — в листе «Фильтры».
 await p.getByRole('button',{name:'Фильтры'}).click();await expect(p.getByRole('dialog',{name:'Фильтры'})).toBeVisible();
 await p.getByRole('link',{name:'Каталог турниров →'}).click();await expect(p.getByRole('heading',{name:'Футбол, который нас объединяет'})).toBeVisible();await guest.close();
});

test('leaders stay within their published tournament edition',async({page,browser})=>{
 test.setTimeout(120000);const seeds=Array.from({length:2},()=>JSON.parse(execFileSync('../.venv/bin/python',['../scripts/seed_rating_e2e.py'],{encoding:'utf8'})));
 await page.goto('/login');await page.getByLabel('Логин',{exact:true}).fill('e2e-analyst');await page.getByLabel('Пароль',{exact:true}).fill('e2e-only-password');await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(page.getByRole('heading',{name:'Турниры',exact:true})).toBeVisible();
 const session=await (await page.request.get('/api/v1/auth/me')).json();const headers={'X-CSRF-Token':session.csrf_token,Origin:new URL(page.url()).origin};
 async function calculate(tid:string,scope:'private'|'public'){const state=await (await page.request.get(`/api/v1/tournaments/${tid}/analytics`)).json();const response=await page.request.post(`/api/v1/tournaments/${tid}/analytics/calculate`,{headers,data:{request_id:crypto.randomUUID(),expected_revision:state.revision,scope}});expect(response.status()).toBe(200);return response.json()}
 const editions=[];for(const s of seeds){const result=await calculate(s.tournament_id,'public');const state=await (await page.request.get(`/api/v1/tournaments/${s.tournament_id}/analytics`)).json();expect((await page.request.post(`/api/v1/tournaments/${s.tournament_id}/analytics/publish`,{headers,data:{request_id:crypto.randomUUID(),expected_revision:state.revision,snapshot_id:result.snapshot_id}})).status()).toBe(200);editions.push(result.snapshot_id)}
 await calculate(seeds[0].tournament_id,'private');
 const guest=await browser.newContext();const p=await guest.newPage();
 for(let i=0;i<2;i++){const tid=seeds[i].tournament_id;await p.goto(`/?day=2020-01-01&tournament_id=${tid}`);const panel=p.locator('.center-leaders');const player=panel.locator('li a').first();await expect(player).toBeVisible();await expect(panel.getByRole('link',{name:'Весь рейтинг'})).toHaveAttribute('href',`/watch/tournaments/${tid}?tab=ratings&snapshot_id=${editions[i]}`);const href=await player.getAttribute('href');expect(href).toContain(`tournament_id=${tid}&snapshot_id=${editions[i]}`);await player.click();await expect(p).toHaveURL(new RegExp(`snapshot_id=${editions[i]}`));await p.goBack();await expect(panel.locator('li')).toHaveCount(5)}
 await p.setViewportSize({width:390,height:844});await expect(p.locator('.center-leaders')).not.toHaveAttribute('open');expect(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await guest.close();
});
