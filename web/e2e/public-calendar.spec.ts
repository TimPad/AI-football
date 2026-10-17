import {test,expect} from '@playwright/test';
import {login,createTournament,task} from './helpers';

test('guest calendar, timetable and VK broadcasts from organizer input',async({page,browser})=>{
 await login(page);const data=await createTournament(page);
 await task(page,'Сведения').click();
 await page.getByLabel('Ссылка на трансляцию ВК',{exact:true}).fill('https://vk.com/video-123_456');
 const embed='https://vk.com/video_ext.php?oid=-123&id=456&hash=test';
 await page.getByLabel('Адрес плеера ВК (src из iframe)',{exact:true}).fill(embed);
 await page.getByRole('button',{name:'Сохранить информацию',exact:true}).click();
 await expect(page.getByText(/Все изменения сохранены/)).toBeVisible();
 await page.reload();await task(page,'Сведения').click();
 await expect(page.getByLabel('Ссылка на трансляцию ВК',{exact:true})).toHaveValue('https://vk.com/video-123_456');
 const guest=await browser.newContext();const viewer=await guest.newPage();const apiRequests:string[]=[];
 viewer.on('request',r=>{if(r.url().includes('/api/'))apiRequests.push(r.url())});
 // A controlled external response verifies iframe wiring; it is not a real broadcast.
 await viewer.route('https://vk.com/video_ext.php**',route=>route.fulfill({contentType:'text/html',body:'<h1>Test player</h1>'}));
 await viewer.goto('/');await expect(viewer.getByRole('heading',{name:'Футбол, который нас объединяет'})).toBeVisible();
 await viewer.goto(`/watch/tournaments/${data.tid}`);
 await expect(viewer.getByRole('link',{name:new RegExp(`${data.home}.*${data.away}`)})).toBeVisible();
 // Один матч в одном зале: фильтры ничего не меняют и не показываются.
 await expect(viewer.locator('.schedule-toolbar')).toHaveCount(0);
 const row=viewer.locator('.schedule-row').first();
 await expect(row).toContainText('19:00');await expect(row).toContainText('Тестовый зал');
 for(const width of [1440,768,375]){
  await viewer.setViewportSize({width,height:1000});
  expect(await viewer.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  // Название команды — в одну строку, ссылка на матч не выходит за карточку.
  for(const name of await row.locator('.slot-team b').all())
   expect(await name.evaluate(e=>e.getBoundingClientRect().height<parseFloat(getComputedStyle(e).fontSize)*2)).toBe(true);
  expect(await row.evaluate(r=>r.querySelector('.slot-open')!.getBoundingClientRect().right<=r.getBoundingClientRect().right)).toBe(true);
  await viewer.screenshot({path:`../data/service/screenshots/public-schedule-${width}.png`,fullPage:true});
 }
 await viewer.getByRole('link',{name:new RegExp(`${data.home}.*${data.away}`)}).click();
 await expect(viewer.getByRole('link',{name:'Смотреть в ВК'})).toHaveAttribute('href','https://vk.com/video-123_456');
 // Без протокола вкладки «События» нет; видео есть — есть и вкладка.
 await expect(viewer.getByRole('navigation',{name:'Разделы матча'}).getByRole('link',{name:'События'})).toHaveCount(0);
 await expect(viewer.getByRole('navigation',{name:'Разделы матча'}).getByRole('link',{name:'Видео'})).toBeVisible();
 await expect(viewer.locator('iframe')).toHaveCount(0);
 await viewer.getByRole('button',{name:'Смотреть на сайте'}).click();
 await expect(viewer.locator('iframe')).toHaveAttribute('src',embed);
 await expect(viewer.frameLocator('iframe').getByRole('heading',{name:'Test player'})).toBeVisible();
 for(const width of [1440,375]){await viewer.setViewportSize({width,height:1000});expect(await viewer.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await viewer.screenshot({path:`../data/service/screenshots/public-match-${width}.png`,fullPage:true})}
 expect(apiRequests.every(url=>url.includes('/api/v1/public/'))).toBe(true);
 await guest.close();
});
