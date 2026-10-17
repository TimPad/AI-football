import {test,expect} from '@playwright/test';
import {login,createTournament} from './helpers';

test('team sheet, images, draft recovery, safe retry and tournament identity',async({page})=>{
 await login(page);const tournament=await createTournament(page);
 const suffix=crypto.randomUUID().slice(0,8);const name=`Команда ${suffix}`,person=`Иван Петров ${suffix}`;
 await page.goto('/teams');await page.getByRole('button',{name:'Создать команду',exact:true}).click();
 await page.getByLabel('Название команды',{exact:true}).fill(name);
 await page.getByLabel('Описание команды',{exact:true}).fill('Ярославль · любительский футзал');
 const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/mNcAAAAASUVORK5CYII=','base64');
 await page.getByLabel('Логотип команды',{exact:true}).setInputFiles({name:'logo.png',mimeType:'image/png',buffer:png});
 await expect(page.getByRole('img',{name:'Логотип команды',exact:true})).toBeVisible();
 await page.getByLabel('ФИО игрока 1',{exact:true}).fill(person);
 await page.getByLabel('Номер игрока 1',{exact:true}).fill('7');
 await page.getByLabel('Амплуа игрока 1',{exact:true}).selectOption('forward');
 await page.getByLabel('Дата рождения игрока 1',{exact:true}).fill('1999-04-10');
 await page.getByLabel('Рост игрока 1',{exact:true}).fill('180');
 await page.getByLabel('Вес игрока 1',{exact:true}).fill('75');
 await page.getByLabel('Фото игрока 1',{exact:true}).setInputFiles({name:'photo.png',mimeType:'image/png',buffer:png});
 await expect(page.getByRole('img',{name:'Фото игрока 1',exact:true})).toBeVisible();
 await page.reload();await expect(page.getByText('Черновик восстановлен',{exact:false})).toBeVisible();
 await expect(page.getByLabel('ФИО игрока 1',{exact:true})).toHaveValue(person);
 let lost=false;const bodies:string[]=[];
 await page.route('**/api/v1/teams',async route=>{if(route.request().method()!=='POST')return route.continue();bodies.push(route.request().postData()!);if(!lost){lost=true;await route.fetch();await route.abort('failed')}else await route.continue()});
 await page.getByRole('button',{name:'Сохранить',exact:true}).click();
 await expect(page.getByRole('button',{name:'Повторить сохранение',exact:true})).toBeVisible();
 await expect(page.getByLabel('Название команды',{exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Повторить сохранение',exact:true}).click();
 await expect(page).toHaveURL(/\/teams\/[0-9a-f-]+$/);expect(bodies).toHaveLength(2);expect(bodies[0]).toBe(bodies[1]);
 const id=new URL(page.url()).pathname.split('/').pop()!;
 const team=await (await page.request.get(`/api/v1/teams/${id}`)).json();const playerId=team.players[0].player_id;
 expect(team.players[0].player.name).toBe(person);expect(team.players[0].player.photo_id).toBeTruthy();
 for(const width of [1440,768,375]){await page.setViewportSize({width,height:1000});await page.evaluate(()=>window.scrollTo(0,0));expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:`../data/service/screenshots/team-profile-${width}.png`,fullPage:true,animations:'disabled'})}
 await page.setViewportSize({width:1440,height:1000});
 await page.goto(`/tournaments/${tournament.tid}?tab=teams`);await page.getByRole('button',{name:'Выбрать существующие',exact:true}).click();await page.getByLabel(name,{exact:true}).check();await page.getByRole('button',{name:/Добавить выбранные/}).click();
 await page.getByRole('row').filter({has:page.getByRole('cell',{name,exact:true})}).getByRole('link',{name:'Игроки и номера →',exact:true}).click();
 await expect(page.getByRole('checkbox',{name:person,exact:true})).toBeChecked();await expect(page.getByLabel(`Номер ${person}`,{exact:true})).toHaveValue('7');
 const rosterPath=new URL(page.url()).pathname.split('/');const entryId=rosterPath[rosterPath.length-1];
 const roster=await (await page.request.get(`/api/v1/entries/${entryId}/players`)).json();expect(roster.players[0].player_id).toBe(playerId);
 // Existing player selection adds membership, not another person.
 await page.goto('/teams/new');await page.getByLabel('Название команды',{exact:true}).fill(`Вторая команда ${suffix}`);await page.getByLabel('Игрок из справочника',{exact:true}).selectOption({label:person});await page.getByRole('button',{name:'Добавить в команду',exact:true}).click();await page.getByRole('button',{name:'Сохранить',exact:true}).click();await expect(page).toHaveURL(/\/teams\/[0-9a-f-]+$/);
 const secondId=new URL(page.url()).pathname.split('/').pop();const second=await (await page.request.get(`/api/v1/teams/${secondId}`)).json();expect(second.players[0].player_id).toBe(playerId);
});
