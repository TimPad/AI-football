import {test,expect} from '@playwright/test';
import {login,createTournament,task,goal} from './helpers';

test('result-only protocol, independent publication and guest path through the match page',async({page,browser})=>{
 await login(page);const data=await createTournament(page);
 await page.getByRole('button',{name:'Только итог',exact:true}).click();
 await expect(page.getByRole('button',{name:'Гол',exact:true})).toHaveCount(0);
 await page.getByLabel('Счёт хозяев',{exact:true}).fill('3');await page.getByLabel('Счёт гостей',{exact:true}).fill('2');
 await page.getByRole('button',{name:'Сохранить итоги',exact:true}).click();await expect(page.getByText(/Все изменения сохранены/)).toBeVisible();
 await page.getByRole('button',{name:'Завершить матч',exact:true}).click();
 await page.getByLabel('Подтверждаю протокол с указанными пропусками').check();
 await page.getByRole('button',{name:'Подтвердить протокол',exact:true}).click();
 await expect(page.getByRole('button',{name:'Открыть для исправления'})).toBeVisible();
 await task(page,'Публикация').click();
 await expect(page.getByRole('heading',{name:'Сейчас видит зритель'})).toBeVisible();
 await expect(page.locator('.guest-sources')).toContainText('не опубликован');
 await page.getByRole('button',{name:'Опубликовать протокол',exact:true}).click();
 await expect(page.locator('.guest-sources')).toContainText('версия 1');
 const guest=await browser.newContext();const viewer=await guest.newPage();const api:string[]=[];
 viewer.on('request',r=>{if(r.url().includes('/api/'))api.push(r.url())});
 await viewer.goto(`/watch/tournaments/${data.tid}`);
 await viewer.getByRole('link',{name:new RegExp(`Открыть матч ${data.home}`)}).click();
 await expect(viewer.getByLabel('Счёт 3 : 2')).toBeVisible();
 await viewer.getByRole('navigation',{name:'Разделы матча'}).getByRole('link',{name:'События',exact:true}).click();
 await expect(viewer.getByText(/Подтверждённый протокол · версия 1/)).toBeVisible();
 await expect(viewer.locator('iframe')).toHaveCount(0);
 for(const width of [1440,1024,390]){await viewer.setViewportSize({width,height:1000});expect(await viewer.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true)}
 expect(api.every(url=>url.includes('/api/v1/public/'))).toBe(true);
 await guest.close();
});

test('a lost protocol response survives report and publication tasks and is sent once',async({page})=>{
 await login(page);const data=await createTournament(page);
 let lose=true;const ids:string[]=[];
 await page.route('**/api/v1/matches/*/commands',async route=>{const body=route.request().postDataJSON();if(body.kind==='add_event')ids.push(body.request_id);
  if(lose&&body.kind==='add_event'){lose=false;await route.fetch();await route.abort('failed')}else await route.continue()});
 await page.getByRole('button',{name:'Гол',exact:true}).click();await page.getByRole('button',{name:'Добавить событие',exact:true}).click();
 await expect(page.getByText(/Несохранённых правок: 1/)).toBeVisible();
 await page.getByRole('dialog').getByRole('button',{name:'Закрыть'}).click();
 await task(page,'Предпросмотр').click();await expect(page.getByText('Отчёт в кабинете')).toBeVisible();
 await task(page,'Публикация').click();await expect(page.getByRole('heading',{name:'Сейчас видит зритель'})).toBeVisible();
 await task(page,'Протокол').click();
 await expect(page.getByText(/Все изменения сохранены/)).toBeVisible();
 expect(new Set(ids).size).toBe(1);
 await expect(page.locator('.journal tbody tr')).toHaveCount(1);
 await page.goto(data.path+'?tab=protocol');await goal(page);await expect(page.locator('.journal tbody tr')).toHaveCount(2);
});

test('an ordinary admin sees protocol tasks only and no Admin+ requests',async({page})=>{
 await login(page);await createTournament(page);const urls:string[]=[];
 page.on('request',r=>{if(r.url().includes('/api/'))urls.push(r.url())});
 const nav=page.getByRole('navigation',{name:'Задачи матча'});
 await expect(nav.getByRole('link',{name:'Участие',exact:true})).toHaveCount(0);
 await expect(nav.getByRole('link',{name:'Действия',exact:true})).toHaveCount(0);
 await task(page,'Публикация').click();
 await expect(page.getByRole('button',{name:'Опубликовать протокол',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Опубликовать видеоанализ',exact:true})).toHaveCount(0);
 await task(page,'Предпросмотр').click();await expect(page.getByText('Отчёт в кабинете')).toBeVisible();
 expect(urls.some(u=>/participation|performance-|analytics|\/ratings|understanding/.test(u)&&!u.includes('/public/'))).toBe(false);
});
