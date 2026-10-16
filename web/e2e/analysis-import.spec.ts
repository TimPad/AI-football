import {task,assignTrack} from './helpers';
import {test,expect} from '@playwright/test';
import {spawnSync} from 'node:child_process';

function packageFor(job:unknown,foreign=false){
 const result=spawnSync('../.venv/bin/python',['-c',"import sys,json; from test_analysis_exchange import result_zip; job=json.load(sys.stdin)\ndef mutate(m,r,t,c):\n for p in r['periods'][0]['players']: p['heatmap_s'][0][0]=1\n if sys.argv[1]=='foreign': m.update(match_id='00000000-0000-0000-0000-000000000001')\nsys.stdout.buffer.write(result_zip(job,mutate=mutate))",foreign?'foreign':'valid'],{input:JSON.stringify(job),env:{...process.env,PYTHONPATH:'../tests'}});
 if(result.status!==0)throw Error(result.stderr.toString());return result.stdout;
}
test('external report → identities → one-match history → separate publication and safe retries',async({page,browser})=>{
 await page.goto('/login');await page.getByLabel('Логин',{exact:true}).fill('e2e-analyst');await page.getByLabel('Пароль',{exact:true}).fill('e2e-only-password');await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(page.getByRole('heading',{name:'Турниры',exact:true})).toBeVisible();
 const session=await (await page.request.get('/api/v1/auth/me')).json();const headers={'X-CSRF-Token':session.csrf_token,Origin:'http://127.0.0.1:8181'};
 async function call(path:string,data:unknown,method='POST'){const r=await page.request.fetch(`/api/v1${path}`,{method,data,headers});expect(r.ok(),await r.text()).toBeTruthy();return r.json()}
 const suffix=crypto.randomUUID().slice(0,6);
 const hall=await call('/halls',{name:`Аналитика ${suffix}`,address:'Тестовый адрес',pitch_length_m:41,pitch_width_m:15.5});
 const camera=await call(`/halls/${hall.id}/camera-profiles`,{name:'Камера',expected_hall_revision:hall.revision,frame_width:1000,frame_height:500,points:[{px:[0,0],m:[0,0]},{px:[999,0],m:[41,0]},{px:[999,499],m:[41,15.5]},{px:[0,499],m:[0,15.5]}],pitch_polygon_px:[[0,0],[999,0],[999,499],[0,499]]});
 const tour=await call('/tournaments',{name:`Импорт ${suffix}`,season:'2026',starts_on:'2026-10-01',ends_on:'2026-12-31'});
 const regulation=await call(`/tournaments/${tour.id}/regulations`,{variant_name:'Группа',rules:{}});
 const entries=[];const lineup=[];const people=[];
 for(const [side,name] of [['home','Север'],['away','Юг']]){
  const team=await call('/teams',{name:`${name} ${suffix}`});const entry=await call(`/tournaments/${tour.id}/entries`,{team_id:team.id});entries.push(entry);
  const person=await call('/players',{name:`Игрок ${name} ${suffix}`});people.push(person);
  const roster=await call(`/entries/${entry.id}/players`,{expected_revision:0,players:[{player_id:person.id,shirt_number:'7'}]},'PUT');lineup.push(...roster.players.map((p:{id:string})=>({entry_player_id:p.id,side})));
 }
 let match=await call(`/tournaments/${tour.id}/matches`,{home_entry_id:entries[0].id,away_entry_id:entries[1].id,regulation_id:regulation.id,scheduled_at:'2026-10-20T18:00:00+03:00',hall_id:hall.id,camera_profile_id:camera.id});
 match=await call(`/matches/${match.id}/commands`,{request_id:crypto.randomUUID(),expected_revision:match.revision,kind:'set_lineup',payload:{players:lineup}});
 const path=`/matches/${match.id}`;await page.goto(path);await task(page,'Проверка').click();
 await page.getByRole('button',{name:'Создать задание',exact:true}).click();await expect(page.getByRole('link',{name:'Скачать job.zip'})).toBeVisible();
 let overview=await (await page.request.get(`/api/v1${path}/analysis`)).json();const job=overview.jobs[0];const raw=packageFor(job);
 const ids:string[]=[];let lose=true;
 await page.route(`**/api/v1${path}/analysis/imports`,async route=>{ids.push(route.request().headers()['x-request-id']);if(lose){lose=false;await route.fetch();await route.abort('failed')}else await route.continue()});
 await page.getByLabel('Пакет результата ZIP').setInputFiles({name:'result.zip',mimeType:'application/zip',buffer:raw});await page.getByRole('button',{name:'Загрузить результат',exact:true}).click();await expect(page.getByRole('button',{name:'Повторить отправку',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Повторить отправку',exact:true}).click();await expect(page.getByLabel('Игрок фрагмента 1')).toBeVisible();expect(ids[0]).toBe(ids[1]);
 for(const id of [1,2])await assignTrack(page,id,people[0].id);await assignTrack(page,3,people[1].id);
 await page.getByRole('button',{name:'Сохранить сопоставление',exact:true}).click();await expect(page.getByRole('button',{name:'Подтвердить аналитику'})).toBeEnabled();
 await page.getByRole('button',{name:'Подтвердить аналитику'}).click();await expect(page.getByRole('heading',{name:'Подтверждённый отчёт'})).toBeVisible();await page.getByText('Показатели этой версии').click();await expect(page.getByRole('cell',{name:'210',exact:true})).toBeVisible();
 const guest=await browser.newContext();const spectator=await guest.newPage();let r=await spectator.request.get(`/api/v1/public${path}/analysis`);expect(r.status()).toBe(404);
 await page.getByRole('button',{name:'Опубликовать аналитику'}).click();await expect(page.getByLabel('Версия отчёта').locator('option:checked')).toContainText('опубликован');
 r=await spectator.request.get(`/api/v1/public${path}/analysis`);expect(r.ok()).toBeTruthy();const published=await r.json();expect(JSON.stringify(published)).not.toContain('track_id');expect(JSON.stringify(published)).not.toContain('context_hash');
 await spectator.goto(`/watch${path}?tab=stats&group=movement`);await expect(spectator.getByRole('heading',{name:'Статистика',exact:true})).toBeVisible();await spectator.getByRole('table',{name:'Показатели игроков'}).getByRole('button',{name:people[0].name,exact:true}).click();
 const mapSize=await spectator.getByRole('dialog',{name:people[0].name}).getByRole('img',{name:/время наблюдения по ячейкам/}).boundingBox();expect(mapSize!.height).toBeGreaterThan(100);
 await page.getByRole('link',{name:`7 · ${people[0].name}`,exact:true}).click();await expect(page.getByText(/1 матчей с активным отчётом/)).toBeVisible();await expect(page.getByRole('cell',{name:'210',exact:true})).toBeVisible();
 await page.goto(path);await task(page,'Проверка').click();
 // A second import does not change publication; confirming it replaces history.
 const second=packageFor(job);await page.getByLabel('Пакет результата ZIP').setInputFiles({name:'second.zip',mimeType:'application/zip',buffer:second});await page.getByRole('button',{name:'Загрузить результат'}).click();await expect(page.getByRole('heading',{name:'На проверке',exact:true})).toBeVisible();
 for(const id of [1,2])await assignTrack(page,id,people[0].id);await assignTrack(page,3,people[1].id);
 await page.getByRole('button',{name:'Сохранить сопоставление'}).click();await expect(page.getByRole('button',{name:'Подтвердить аналитику'})).toBeEnabled();await page.getByRole('button',{name:'Подтвердить аналитику'}).click();await expect(page.getByRole('heading',{name:'Подтверждённый отчёт'})).toBeVisible();
 const history=await (await page.request.get(`/api/v1/players/${people[0].id}/analysis`)).json();expect(history.match_count).toBe(1);expect(history.totals.distance_m).toBe(210);
 expect((await (await spectator.request.get(`/api/v1/public${path}/analysis`)).json()).run_id).toBe(published.run_id);
 await page.getByLabel('Пакет результата ZIP').setInputFiles({name:'foreign.zip',mimeType:'application/zip',buffer:packageFor(job,true)});await page.getByRole('button',{name:'Загрузить результат'}).click();await expect(page.getByRole('alert')).toBeVisible();expect((await (await spectator.request.get(`/api/v1/public${path}/analysis`)).json()).run_id).toBe(published.run_id);
 await spectator.goto('/login');await spectator.getByLabel('Логин',{exact:true}).fill('e2e-admin');await spectator.getByLabel('Пароль',{exact:true}).fill('e2e-only-password');await spectator.getByRole('button',{name:'Войти',exact:true}).click();await expect(spectator.getByRole('heading',{name:'Турниры',exact:true})).toBeVisible();await spectator.goto(path);await task(spectator,'Проверка').click();await expect(spectator.getByText(/Для выдачи заданий/)).toBeVisible();await expect(spectator.getByRole('button',{name:'Создать задание'})).toHaveCount(0);
 await guest.close();
});
