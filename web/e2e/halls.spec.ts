import {test,expect} from '@playwright/test';
import {login,createTournament,task} from './helpers';

test('hall geometry, camera version, match binding and CV download',async({page})=>{
 await login(page);const data=await createTournament(page);
 await page.goto(`/halls/${data.hallId}`);
 await expect(page.getByLabel('Широта',{exact:true})).toHaveCount(0);await expect(page.getByLabel('Долгота',{exact:true})).toHaveCount(0);
 const hallAddress=await page.getByLabel('Адрес зала',{exact:true}).inputValue();await expect(page.getByRole('link',{name:'Открыть в Яндекс Картах',exact:true})).toHaveAttribute('href',`https://yandex.ru/maps/?text=${encodeURIComponent(hallAddress)}`);
 await page.getByLabel('Покрытие',{exact:true}).fill('Паркет');await page.getByLabel('Описание зала',{exact:true}).fill('Камера на балконе');
 await page.getByRole('button',{name:'Сохранить зал',exact:true}).click();
 await expect(page.getByText('Ввод сохранён в черновике',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Добавить профиль камеры',exact:true}).click();
 await page.getByLabel('Ширина кадра, px',{exact:true}).fill('1000');await page.getByLabel('Высота кадра, px',{exact:true}).fill('500');
 const points=[[0,0],[999,0],[999,499],[0,499]];
 for(let i=0;i<points.length;i++){await page.getByLabel(`Точка ${i+1}: X кадра`,{exact:true}).fill(String(points[i][0]));await page.getByLabel(`Точка ${i+1}: Y кадра`,{exact:true}).fill(String(points[i][1]))}
 await page.reload();await page.getByRole('button',{name:'Добавить профиль камеры',exact:true}).click();
 await expect(page.getByLabel('Точка 3: Y кадра',{exact:true})).toHaveValue('499');
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
 await expect(viewer.getByText(/Ярославль, Спортивная.*поле 41 × 15.5 м/)).toBeVisible();await expect(viewer.getByRole('link',{name:'Открыть в Яндекс Картах',exact:true})).toHaveAttribute('href',`https://yandex.ru/maps/?text=${encodeURIComponent(hallAddress)}`);await guest.close();
});
