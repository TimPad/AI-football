import {test,expect} from '@playwright/test';
import {login,createTournament,task} from './helpers';

// Синтетический кадр с белой рамкой «поля» — рисуется в браузере, без файлов в репозитории.
async function openImage(page:import('@playwright/test').Page,w:number,h:number){
 const png=await page.evaluate(([w,h])=>{const c=document.createElement('canvas');c.width=w;c.height=h;const g=c.getContext('2d')!;g.fillStyle='#2a6';g.fillRect(0,0,w,h);g.strokeStyle='#fff';g.lineWidth=4;g.strokeRect(w*0.05,h*0.1,w*0.9,h*0.8);return c.toDataURL('image/png').split(',')[1]},[w,h]);
 await page.locator('label',{hasText:/картин/}).locator('input').setInputFiles({name:'frame.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});
 await expect(page.getByRole('img',{name:'Разметка точек на кадре'})).toBeVisible();
}
const cornersOf=(w:number,h:number)=>[[w*0.05,h*0.1],[w*0.95,h*0.1],[w*0.95,h*0.9],[w*0.05,h*0.9]];
async function markCorners(page:import('@playwright/test').Page,w:number,h:number){
 const stage=page.getByRole('img',{name:'Разметка точек на кадре'});const box=(await stage.boundingBox())!;
 for(const [x,y] of cornersOf(w,h))await stage.click({position:{x:x/w*box.width,y:y/h*box.height}});
 await expect(page.getByText('Все точки отмечены',{exact:false})).toBeVisible();
}

test('hall geometry, camera version, match binding and CV download',async({page})=>{
 await login(page);const data=await createTournament(page);
 await page.goto(`/halls/${data.hallId}`);
 await expect(page.getByLabel('Широта',{exact:true})).toHaveCount(0);await expect(page.getByLabel('Долгота',{exact:true})).toHaveCount(0);
 const hallAddress=await page.getByLabel('Адрес зала',{exact:true}).inputValue();await expect(page.getByRole('link',{name:'Открыть в Яндекс Картах',exact:true})).toHaveAttribute('href',`https://yandex.ru/maps/?text=${encodeURIComponent(hallAddress)}`);
 await page.getByLabel('Покрытие',{exact:true}).fill('Паркет');await page.getByLabel('Описание зала',{exact:true}).fill('Камера на балконе');
 await page.getByRole('button',{name:'Сохранить зал',exact:true}).click();
 await expect(page.getByText('Ввод сохранён в черновике',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Добавить профиль камеры',exact:true}).click();
 // Кадр 1000×500, углы отмечаются кликами; после перезагрузки точки берутся из черновика, кадр выбирается заново.
 await openImage(page,1000,500);await markCorners(page,1000,500);
 await page.reload();await page.getByRole('button',{name:'Добавить профиль камеры',exact:true}).click();
 await openImage(page,1000,500);await expect(page.getByText('Все точки отмечены',{exact:false})).toBeVisible();
 let lost=false;const bodies:string[]=[];
 await page.route(`**/api/v1/halls/${data.hallId}/camera-profiles`,async route=>{if(route.request().method()!=='POST')return route.continue();bodies.push(route.request().postData()!);if(!lost){lost=true;await route.fetch();await route.fulfill({status:201,contentType:'application/json',body:'{'})}else await route.continue()});
 await page.getByRole('button',{name:'Сохранить профиль камеры',exact:true}).click();
 await expect(page.getByRole('button',{name:'Повторить сохранение профиля',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Повторить сохранение профиля',exact:true}).click();
 await expect(page.locator('summary').filter({hasText:'Основная камера · версия 1'})).toBeVisible();expect(bodies).toHaveLength(2);expect(bodies[0]).toBe(bodies[1]);
 await page.locator('summary').filter({hasText:'Основная камера · версия 1'}).click();
 for(const width of [1440,768,375]){await page.setViewportSize({width,height:1000});await page.evaluate(()=>window.scrollTo(0,0));expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:`../data/service/screenshots/hall-${width}.png`,fullPage:true,animations:'disabled'})}
 await page.setViewportSize({width:1440,height:1000});
 await page.goto(data.path);await task(page,'Сведения').click();
 await expect(page.getByLabel('Зал',{exact:true})).toHaveValue(data.hallId);
 await page.getByLabel('Профиль камеры',{exact:true}).selectOption({label:'Основная камера · версия 1 · 1000 × 500 px'});
 await page.getByRole('button',{name:'Сохранить информацию',exact:true}).click();
 await expect(page.getByText(/Все изменения сохранены/)).toBeVisible();
 const download=page.waitForEvent('download');await page.getByRole('link',{name:'Скачать координаты для CV',exact:true}).click();
 const file=await download;expect(file.suggestedFilename()).toMatch(/^cv-.*\.zip$/);expect(await file.failure()).toBeNull();
 const matchId=data.path.split('/').pop()!;
 const match=await (await page.request.get(`/api/v1/matches/${matchId}`)).json();
 expect(match.hall_snapshot.pitch_length_m).toBe(41);expect(match.camera_profile_id).toBeTruthy();
 // A catalog correction cannot silently change the saved match geometry.
 await page.goto(`/halls/${data.hallId}`);await page.getByLabel('Длина поля, м',{exact:true}).fill('42');await page.getByRole('button',{name:'Сохранить зал',exact:true}).click();
 await expect(page.getByText(/прежние размеры поля/)).toBeVisible();
 await page.goto(data.path);await task(page,'Сведения').click();
 await expect(page.getByText(/Поле: 41 × 15.5 м/)).toBeVisible();await expect(page.getByLabel('Профиль камеры',{exact:true})).toHaveValue(match.camera_profile_id);
 const guest=await page.context().browser()!.newContext();const viewer=await guest.newPage();await viewer.goto(`/watch/matches/${matchId}`);
 // Зрителю — адрес без технических размеров поля.
 await expect(viewer.getByText(/Ярославль, Спортивная/)).toBeVisible();await expect(viewer.getByText(/поле 41/)).toHaveCount(0);await expect(viewer.getByRole('link',{name:'Открыть в Яндекс Картах',exact:true})).toHaveAttribute('href',`https://yandex.ru/maps/?text=${encodeURIComponent(hallAddress)}`);await guest.close();
});

test('camera points are marked by clicking a frame, which becomes the reference frame',async({page})=>{
 await login(page);const data=await createTournament(page);
 await page.goto(`/halls/${data.hallId}`);await page.getByRole('button',{name:'Добавить профиль камеры',exact:true}).click();
 await openImage(page,800,400);await markCorners(page,800,400);await page.locator('.camera-editor').screenshot({path:'test-results/camera-click.png'});
 await page.getByRole('button',{name:'Сохранить профиль камеры',exact:true}).click();
 const summary=page.locator('summary').filter({hasText:'Основная камера · версия 1'});await expect(summary).toBeVisible();await summary.click();
 await expect(page.getByRole('img',{name:'Эталонный кадр камеры «Основная камера», версия 1'})).toBeVisible();
 const [profile]=(await (await page.request.get(`/api/v1/halls/${data.hallId}/camera-profiles`)).json()).items;const corners=cornersOf(800,400);
 expect([profile.frame_width,profile.frame_height]).toEqual([800,400]);expect(profile.reference_sha256).toMatch(/^[0-9a-f]{64}$/);
 profile.points.forEach((p:{px:number[]},i:number)=>{expect(Math.abs(p.px[0]-corners[i][0])).toBeLessThanOrEqual(2);expect(Math.abs(p.px[1]-corners[i][1])).toBeLessThanOrEqual(2)});
});

test('a frame is taken from the recording itself in its own resolution',async({page})=>{
 await login(page);const data=await createTournament(page);
 await page.goto(`/halls/${data.hallId}`);await page.getByRole('button',{name:'Добавить профиль камеры',exact:true}).click();
 // Короткая синтетическая запись 640×360 (WebM из canvas): видео в репозиторий не добавляется.
 const webm=await page.evaluate(async()=>{const c=document.createElement('canvas');c.width=640;c.height=360;const g=c.getContext('2d')!;
  const rec=new MediaRecorder(c.captureStream(10),{mimeType:'video/webm'});const parts:Blob[]=[];rec.ondataavailable=e=>parts.push(e.data);
  let frame=0;const draw=setInterval(()=>{g.fillStyle='#2a6';g.fillRect(0,0,640,360);g.fillStyle='#fff';g.fillRect(40+frame++%50,40,20,20)},100);
  rec.start();await new Promise(r=>setTimeout(r,1200));rec.stop();await new Promise(r=>rec.onstop=r);clearInterval(draw);
  const bytes=new Uint8Array(await new Blob(parts,{type:'video/webm'}).arrayBuffer());let text='';bytes.forEach(b=>text+=String.fromCharCode(b));return btoa(text)});
 await page.locator('label',{hasText:'Взять кадр из записи'}).locator('input').setInputFiles({name:'match.webm',mimeType:'video/webm',buffer:Buffer.from(webm,'base64')});
 await expect(page.getByRole('img',{name:'Разметка точек на кадре'})).toBeVisible();
 await expect(page.getByText(/Кадр 640 × 360 px/)).toBeVisible();
 await expect(page.getByText(/Для специалиста/)).toHaveCount(0);
});
