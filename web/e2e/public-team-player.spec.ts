import {test,expect} from '@playwright/test';
import {login,createTournament} from './helpers';
test('published team and player preserve the viewer path and calendar filters without ratings',async({page,browser})=>{
 await login(page);const data=await createTournament(page);const origin=new URL(page.url()).origin;
 const auth=await (await page.request.get('/api/v1/auth/me')).json();const headers={'Origin':origin,'X-CSRF-Token':auth.csrf_token};
 async function call(path:string,body?:unknown,method='POST'){const r=body===undefined?await page.request.get('/api/v1'+path):await page.request.fetch('/api/v1'+path,{method,headers,data:body});expect(r.ok(),await r.text()).toBe(true);return r.json()}
 let match=await call(data.path);const name='Игрок с очень длинным опубликованным именем без рейтинга';const player=await call('/players',{name});
 const roster=await call(`/entries/${match.home_entry_id}/players`,{expected_revision:0,players:[{player_id:player.id,shirt_number:'7'}]},'PUT');
 async function command(kind:string,payload:unknown){match=await call(`${data.path}/commands`,{request_id:crypto.randomUUID(),expected_revision:match.revision,kind,payload})}
 await command('set_lineup',{players:[{entry_player_id:roster.players[0].id,side:'home'}]});
 await command('set_totals',{reported_totals:{home:{score:0},away:{score:0}}});await command('set_status',{status:'ended'});await command('confirm',{acknowledge_incomplete:true});const version=(await call(data.path+'/versions')).items[0];await command('publish',{version_id:version.id});
 const team=match.home.team_id;const guest=await browser.newContext();const viewer=await guest.newPage();
 const initial=`/watch/tournaments/${data.tid}?day=2026-10-20&hall_id=${data.hallId}&team_id=${team}`;
 await viewer.goto(initial);await expect(viewer.getByLabel('Счёт 0 : 0')).toBeVisible();await viewer.locator('.schedule-row').getByRole('link',{name:data.home,exact:true}).click();
 await expect(viewer.getByRole('heading',{name:data.home,exact:true})).toBeVisible();await viewer.getByRole('link',{name:new RegExp('Открыть матч')}).click();await viewer.getByRole('link',{name:'Составы',exact:true}).click();await viewer.getByRole('button',{name:new RegExp(name)}).click();await viewer.getByRole('link',{name:'Карточка игрока и история →',exact:true}).click();
 await expect(viewer.getByRole('heading',{name,exact:true})).toBeVisible();await expect(viewer.getByRole('heading',{name:'Опубликованные выступления'})).toBeVisible();
 for(const width of [1440,1024,390]){await viewer.setViewportSize({width,height:900});expect(await viewer.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await viewer.screenshot({path:`test-results/public-player-${width}.png`,fullPage:true,animations:'disabled'})}
 await viewer.getByRole('link',{name:'← К матчу',exact:true}).click();await viewer.reload();await viewer.getByRole('button',{name:'Закрыть карточку игрока',exact:true}).click();await viewer.getByRole('link',{name:'← К команде',exact:true}).click();await viewer.getByRole('link',{name:'← К турниру',exact:true}).click();await expect(viewer).toHaveURL(origin+initial);
 await page.goto(`/tournaments/${data.tid}`);const t=await call(`/tournaments/${data.tid}`);await call(`/tournaments/${data.tid}`,{expected_revision:t.revision,archived:true},'PATCH');expect((await viewer.request.get(`/api/v1/public/players/${player.id}?tournament_id=${data.tid}`)).status()).toBe(404);await guest.close();
});
